import celery
from database import db
from database import Deployment
from lib.config.cluster_config import CLUSTER_CONFIG
from redlock import RedLock
import os
import shutil
from lib.dgs121028p import turn_on_port, turn_off_port
import time
import paramiko
from paramiko.ssh_exception import BadHostKeyException, AuthenticationException, SSHException
import socket
from lib.deployment import get_nfs_boot_cmdline, get_sdcard_boot_cmdline, get_sdcard_resize_boot_cmdline
import re
from celery.utils.log import get_task_logger
import logging
from celery.signals import after_setup_task_logger
from celery.app.log import TaskFormatter
from contextlib import contextmanager
from redlock.lock import RedLockError

logger = get_task_logger(__name__)
logger.setLevel(logging.INFO)


@after_setup_task_logger.connect
def setup_task_logger(logger, *args, **kwargs):
    for handler in logger.handlers:
        handler.setFormatter(TaskFormatter('%(asctime)s - %(levelname)s - %(processName)s - [%(task_name)s:%(lineno)d] - %(message)s'))


POSTINSTALL_CMDS = """\
#!/bin/bash

systemctl enable ssh
service ssh start

echo "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDDjXBuWj8MJuGcJDx1/ch7nDBptyoXjBP3DNQPel+A+sI/76dT/MPw6HgUxywb0aJ1L50QU0xDU/dhl0er4WK31DLf6QR2ursZ7yYhgrRm8uugYEIYxs8qu5SyNXiNPOTnH+Pd+IUt/T3iqyrPLOifnuqWaeN26WqUlWiAcqIrJdfl+KgNuYOS4u3bFNEPBuab3wqi8JREkv25j9NJ7UMrVUzhQ8eMeCQmQsoVBsMwfhLZ/DyZz4o/+IsP05AmJs0q3eJJwsFSWerZTNtes97qkD/H+RQv5VhGqYKncyCoFHt0D4lstFizlG/1rxow6scssQR2dfs1XSuc6VHCnuLv root@nuc1" >> /root/.ssh/authorized_keys 

exit 0
"""


def ignore_failed_lock_acquisition(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except RedLockError as e:
            logger.info("Could not get acquire the lock")

    return wrapper


@ignore_failed_lock_acquisition
@celery.task()
def prepare_nfs_boot():
    logger.debug("Checking deployments in 'created' state")

    # Use lock in context
    with RedLock("lock/deployments/created"):
        pending_deployments = Deployment.query.filter_by(state="created").all()
        logger.debug(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            # Create a folder containing network boot files that will be served via TFTP
            tftpboot_template_folder = "/tftpboot/rpiboot"
            tftpboot_node_folder = "/tftpboot/%s" % server.get("id")

            if os.path.isdir(tftpboot_node_folder):
                shutil.rmtree(tftpboot_node_folder)
            shutil.copytree(tftpboot_template_folder, tftpboot_node_folder)

            # Modify the boot PXE configuration file to mount its file system via NFS
            text_file = open("%s/cmdline.txt" % tftpboot_node_folder, "w")
            text_file.write(get_nfs_boot_cmdline() % {"controller_ip": CLUSTER_CONFIG.get("controller").get("ip")})
            text_file.close()

            # Update the deployment
            deployment.prepare_nfs_boot()
            db.session.add(deployment)
            db.session.commit()

            logger.info(f"deployment {deployment.id}: 'created' => 'configured_nfs_boot'")
        db.session.remove()


@ignore_failed_lock_acquisition
@celery.task()
def init_reboot_nfs():
    logger.debug("Checking deployments in 'configured_nfs_boot' state")

    # Use lock in context
    with RedLock("lock/deployments/configured_nfs_boot"):
        pending_deployments = Deployment.query.filter_by(state="configured_nfs_boot").all()
        logger.debug(len(pending_deployments))

        for deployment in pending_deployments:
            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            # Turn off port
            turn_off_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))

            # Wait 2 seconds
            time.sleep(2)

            # Turn on port
            turn_on_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))

            # Update the deployment
            deployment.init_reboot_nfs()
            db.session.add(deployment)
            db.session.commit()
            logger.info(f"deployment {deployment.id}: 'configured_nfs_boot' => 'nfs_rebooting'")
        db.session.remove()


@ignore_failed_lock_acquisition
@celery.task()
def conclude_reboot_nfs():
    logger.debug("Checking deployments in 'nfs_rebooting' state")

    # Use lock in context
    with RedLock("lock/deployments/nfs_rebooting"):
        pending_deployments = Deployment.query.filter_by(state="nfs_rebooting").all()
        logger.debug(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            logger.info(server)

            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(server.get("ip"), username="root", timeout=1.0)
                logger.info("Could connect to %s" % server.get("ip"))

                # Update the deployment
                deployment.conclude_reboot_nfs()
                db.session.add(deployment)
                db.session.commit()

                logger.info(f"deployment {deployment.id}: 'nfs_rebooting' => 'nfs_rebooted'")

            except (BadHostKeyException, AuthenticationException,
                    SSHException, socket.error) as e:
                logger.info(e)
                logger.info("Could not connect to %s" % server.get("ip"))
        db.session.remove()


@ignore_failed_lock_acquisition
@celery.task()
def prepare_deployment():
    logger.debug("Checking deployments in 'nfs_rebooted' state")

    # Use lock in context
    with RedLock("lock/deployments/nfs_rebooted"):
        pending_deployments = Deployment.query.filter_by(state="nfs_rebooted").all()
        logger.debug(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            logger.info(server)

            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(server.get("ip"), username="root")
                logger.info("Could connect to %s" % server.get("ip"))

                # Create folder for mounting the sd card
                ssh.exec_command("mkdir -p /tmp/sdcard_boot")
                ssh.exec_command("mkdir -p /tmp/sdcard_fs")

                # Update the deployment
                deployment.prepared_deployment()
                db.session.add(deployment)
                db.session.commit()

                logger.info(f"deployment {deployment.id}: 'nfs_rebooted' => 'ready_deploy'")

            except (BadHostKeyException, AuthenticationException,
                    SSHException, socket.error) as e:
                logger.info(e)
                logger.info("Could not connect to %s" % server.get("ip"))
        db.session.remove()


@ignore_failed_lock_acquisition
@celery.task()
def deploy_env():
    logger.debug("Checking deployments in 'ready_deploy' state")

    # Use lock in context
    with RedLock("lock/deployments/ready_deploy"):
        pending_deployments = Deployment.query.filter_by(state="ready_deploy").all()
        logger.debug(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
            environment = [environment for environment in CLUSTER_CONFIG.get("environments") if
                           environment.get("name") == deployment.environment][0]
            environment_local_path = environment.get("nfs_path")
            logger.info("environment_local_path: %s" % (environment_local_path))

            logger.info(server)

            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(server.get("ip"), username="root", timeout=1.0)
                logger.info("Could connect to %s" % server.get("ip"))

                # Write the image of the environment on SD card
                # deploy_cmd = """rm /tmp/deployment_done; unzip -p %s | sudo dd of=/dev/mmcblk0 bs=4M conv=fsync status=progress 2>&1 | tee /tmp/progress.txt; touch /tmp/deployment_done;""" % (environment_local_path)
                deploy_cmd = f"""rm /tmp/deployment_done; rm /tmp/progress_{server['id']}.txt; rsh 192.168.1.22 "pigz -dc /nfs/raspi1/{environment_local_path}" | sudo dd of=/dev/mmcblk0 bs=4M conv=fsync status=progress 2>&1 | tee /tmp/progress_{server['id']}.txt; touch /tmp/deployment_done;"""

                screen_deploy_cmd = "screen -d -m bash -c '%s'" % deploy_cmd
                logger.info(screen_deploy_cmd)

                ssh.exec_command(screen_deploy_cmd)

                # Update the deployment
                deployment.deploy_env()
                db.session.add(deployment)
                db.session.commit()

                logger.info(f"deployment {deployment.id}: 'ready_deploy' => 'environment_deploying'")

            except (BadHostKeyException, AuthenticationException,
                    SSHException, socket.error) as e:
                logger.info(e)
                logger.info("Could not connect to %s" % server.get("ip"))
        db.session.remove()


@ignore_failed_lock_acquisition
@celery.task()
def deploy_env_finished():
    logger.debug("Checking deployments in 'environment_deploying' state")

    # Use lock in context
    with RedLock("lock/deployments/environment_deploying"):
        pending_deployments = Deployment.query.filter_by(state="environment_deploying").all()
        logger.debug(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(server.get("ip"), username="root", timeout=1.0)
                logger.info("Could connect to %s" % server.get("ip"))

                # Write the image of the environment on SD card
                ftp = ssh.open_sftp()
                logger.info(ftp)

                if "deployment_done" in ftp.listdir("/tmp"):
                    # Update the deployment
                    deployment.deploy_env_finished()
                    logger.info(f"deployment {deployment.id}: 'environment_deploying' => 'environment_deployed'")
                else:
                    # Get the progress
                    if f"progress_{server['id']}.txt" in ftp.listdir("/tmp"):
                        cmd = f"""cat /tmp/progress_{server['id']}.txt"""
                        (stdin, stdout, stderr) = ssh.exec_command(cmd)
                        lines = stdout.readlines()
                        sublines = [sl.strip() for l in lines for sl in l.split("\r")]
                        output = re.sub('[^ a-zA-Z0-9./,()]', '', sublines[-1])
                        deployment.label = output

                        logger.info(f"{server.get('ip')} ({deployment.id}) => {output}")
                    else:
                        logger.info(f"{server.get('ip')} ({deployment.id}) : NO /tmp/progress_{server['id']}.txt file!!!")

                ssh.close()

                db.session.add(deployment)
                db.session.commit()


            except (BadHostKeyException, AuthenticationException,
                    SSHException, socket.error) as e:
                logger.info(e)
                logger.info("Could not connect to %s" % server.get("ip"))
        db.session.remove()


@ignore_failed_lock_acquisition
@celery.task()
def configure_sdcard_resize_boot():
    logger.debug("Checking deployments in 'environment_deployed' state")

    # Use lock in context
    with RedLock("lock/deployments/environment_deployed"):
        pending_deployments = Deployment.query.filter_by(state="environment_deployed").all()
        logger.debug(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            try:
                logger.info("<start>")

                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(server.get("ip"), username="root", timeout=1.0)
                logger.info("Could connect to %s" % server.get("ip"))

                long_cmd = """
#!/bin/bash

if [ ! -d /tmp/sdcard_boot ]; then
    mkdir -p /tmp/sdcard_boot
fi

if [ ! -d /tmp/sdcard_fs ]; then
    mkdir -p /tmp/sdcard_fs
fi

if [[ $(findmnt  | grep "sdcard_boot") ]]; then
    umount /tmp/sdcard_boot
fi

if [[ $(findmnt  | grep "sdcard_fs") ]]; then
    umount /tmp/sdcard_fs
fi

mount /dev/mmcblk0p1 /tmp/sdcard_boot
mount /dev/mmcblk0p2 /tmp/sdcard_fs

mv /tmp/sdcard_boot/bootcode.bin /tmp/sdcard_boot/_bootcode.bin
echo '1' > /tmp/sdcard_boot/ssh

if [[ $(findmnt  | grep "sdcard_boot") ]]; then
    umount /tmp/sdcard_boot
fi

if [[ $(findmnt  | grep "sdcard_fs") ]]; then
    umount /tmp/sdcard_fs
fi

mount /dev/mmcblk0p1 /tmp/sdcard_boot
mount /dev/mmcblk0p2 /tmp/sdcard_fs

"""
                ssh.exec_command(long_cmd)

                ftp = ssh.open_sftp()
                logger.info(ftp)

                # Modify the boot PXE configuration file to resize the FS
                tftpboot_node_folder = "/tftpboot/%s" % server.get("id")
                text_file = open("%s/cmdline.txt" % tftpboot_node_folder, "w")
                text_file.write(get_sdcard_resize_boot_cmdline())
                text_file.close()

                # # /!\ here we check that changes have been committed to the SD card
                #
                # # Mount the boot partition of the SD CARD
                # cmd = "mount /dev/mmcblk0p1 /tmp/sdcard_boot"
                # ssh.exec_command(cmd)

                # Wait 2 second
                time.sleep(2)

                successful_step = True

                if "_bootcode.bin" not in ftp.listdir("/tmp/sdcard_boot"):
                    logger.info("bootcode.bin file has not been renamed!")
                    successful_step = False

                if "ssh" not in ftp.listdir("/tmp/sdcard_boot"):
                    logger.info("ssh file has not been created!")
                    successful_step = False

                # Unmount the boot partition of the SD CARD
                cmd = "umount /tmp/sdcard_boot"
                ssh.exec_command(cmd)

                # Update the deployment
                if successful_step:
                    deployment.configure_sdcard_resize_boot()
                    db.session.add(deployment)
                    db.session.commit()

                    logger.info(f"deployment {deployment.id}: 'environment_deployed' => 'configured_sdcard_resize_boot'")

                logger.info("<end>")

            except (BadHostKeyException, AuthenticationException,
                    SSHException, socket.error) as e:
                logger.info(e)
                logger.info("Could not connect to %s" % server.get("ip"))
        db.session.remove()


@ignore_failed_lock_acquisition
@celery.task()
def init_reboot_nfs_after_resize():
    logger.debug("Checking configured_nfs_boot in 'configured_sdcard_resize_boot' state")

    # Use lock in context
    with RedLock("lock/deployments/configured_sdcard_resize_boot"):
        pending_deployments = Deployment.query.filter_by(state="configured_sdcard_resize_boot").all()
        logger.debug(len(pending_deployments))

        if len(pending_deployments):
            for deployment in pending_deployments:
                # Get description of the server that will be deployed
                server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][
                    0]

                # Turn off port
                turn_off_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))

                # Wait 2 seconds
                time.sleep(2)

                # Turn on port
                turn_on_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))

            # Wait 40 seconds to let the FS to resize
            time.sleep(40)

            for deployment in pending_deployments:
                # Get description of the server that will be deployed
                server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][
                    0]

                # Modify the boot PXE configuration file to resize the FS
                tftpboot_node_folder = "/tftpboot/%s" % server.get("id")
                text_file = open("%s/cmdline.txt" % tftpboot_node_folder, "w")
                text_file.write(get_nfs_boot_cmdline() % {"controller_ip": CLUSTER_CONFIG.get("controller").get("ip")})
                text_file.close()

                # Turn off port
                turn_off_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))

                # Wait 2 seconds
                time.sleep(2)

                # Turn on port
                turn_on_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))

                # Update the deployment
                deployment.init_reboot_nfs_after_resize()
                db.session.add(deployment)
                db.session.commit()

                logger.info(f"deployment {deployment.id}: 'configured_sdcard_resize_boot' => 'nfs_rebooting_after_resize'")
        db.session.remove()


@ignore_failed_lock_acquisition
@celery.task()
def conclude_reboot_nfs_after_resize():
    logger.debug("Checking deployments in 'nfs_rebooting_after_resize' state")

    # Use lock in context
    with RedLock("lock/deployments/nfs_rebooting_after_resize"):
        pending_deployments = Deployment.query.filter_by(state="nfs_rebooting_after_resize").all()
        logger.debug(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            logger.info(server)

            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(server.get("ip"), username="root", timeout=1.0)
                logger.info("Could connect to %s" % server.get("ip"))

                # Update the deployment
                deployment.conclude_reboot_nfs_after_resize()
                db.session.add(deployment)
                db.session.commit()

                logger.info(f"deployment {deployment.id}: 'nfs_rebooting_after_resize' => 'nfs_rebooted_after_resize'")

            except (BadHostKeyException, AuthenticationException,
                    SSHException, socket.error) as e:
                logger.info(e)
                logger.info("Could not connect to %s" % server.get("ip"))
        db.session.remove()


@ignore_failed_lock_acquisition
@celery.task()
def collect_partition_uuid():
    logger.debug("Checking deployments in 'nfs_rebooted_after_resize' state")

    # Use lock in context
    with RedLock("lock/deployments/nfs_rebooted_after_resize"):
        pending_deployments = Deployment.query.filter_by(state="nfs_rebooted_after_resize").all()
        logger.debug(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(server.get("ip"), username="root", timeout=1.0)
                logger.info("Could connect to %s" % server.get("ip"))

                successful_step = True

                # Ensure 'sdcard_boot' exists
                ssh.exec_command("mkdir -p /tmp/sdcard_boot")

                # Unmount the boot file system
                cmd = "umount /tmp/sdcard_fs"
                ssh.exec_command(cmd)

                # Mount the boot partition of the SD CARD
                cmd = "mount /dev/mmcblk0p2 /tmp/sdcard_fs"
                ssh.exec_command(cmd)

                # Sleep 2 seconds
                time.sleep(2)

                # Check the size of the partition : if it is small, go back to 'environment_deployed' state
                cmd = """lsblk | grep mmcblk0p2 | awk '{print $4}' | sed 's/G//g'"""
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                output = stdout.readlines()
                partition_size = float(output[0].strip())

                # Check if resize has been successful (partition's size should be larger than 4 GB)
                if partition_size < 4.0:
                    successful_step = False

                # Unmount the boot partition of the SD CARD
                cmd = "umount /tmp/sdcard_boot"
                ssh.exec_command(cmd)

                # Update the deployment
                if successful_step:
                    deployment.collect_partition_uuid()
                else:
                    deployment.retry_resize()

                db.session.add(deployment)
                db.session.commit()

                logger.info(f"deployment {deployment.id}: 'nfs_rebooted_after_resize' => 'collected_partition_uuid'")

            except (BadHostKeyException, AuthenticationException,
                    SSHException, socket.error) as e:
                logger.info(e)
                logger.info("Could not connect to %s" % server.get("ip"))
        db.session.remove()


@ignore_failed_lock_acquisition
@celery.task()
def deploy_public_key():
    logger.debug("Checking deployments in 'collected_partition_uuid' state")

    # Use lock in context
    with RedLock("lock/deployments/collected_partition_uuid"):
        pending_deployments = Deployment.query.filter_by(state="collected_partition_uuid").all()
        logger.debug(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(server.get("ip"), username="root", timeout=1.0)
                logger.info("Could connect to %s" % server.get("ip"))

                long_cmd = f"""
#!/bin/bash

if [ ! -d /tmp/sdcard_boot ]; then
    mkdir -p /tmp/sdcard_boot
fi

if [ ! -d /tmp/sdcard_fs ]; then
    mkdir -p /tmp/sdcard_fs
fi

if [[ $(findmnt  | grep "sdcard_boot") ]]; then
    umount /tmp/sdcard_boot
fi

if [[ $(findmnt  | grep "sdcard_fs") ]]; then
    umount /tmp/sdcard_fs
fi

mount /dev/mmcblk0p1 /tmp/sdcard_boot
mount /dev/mmcblk0p2 /tmp/sdcard_fs

# Do something here

mkdir -p /tmp/sdcard_fs/root/.ssh
cp /root/.ssh/authorized_keys /tmp/sdcard_fs/root/.ssh/authorized_keys

echo '{CLUSTER_CONFIG.get("controller").get("public_key")}' >> /tmp/sdcard_fs/root/.ssh/authorized_keys
echo '{deployment.public_key}' >> /tmp/sdcard_fs/root/.ssh/authorized_keys

# Add the public key of the user
echo '{deployment.public_key}' >> /tmp/sdcard_fs/root/.ssh/authorized_keys

cat << EOF > /tmp/sdcard_fs/etc/rc.local
{POSTINSTALL_CMDS}
EOF

chmod +x /tmp/sdcard_fs/etc/rc.local          

if [[ $(findmnt  | grep "sdcard_boot") ]]; then
    umount /tmp/sdcard_boot
fi

if [[ $(findmnt  | grep "sdcard_fs") ]]; then
    umount /tmp/sdcard_fs
fi
"""
                ssh.exec_command(long_cmd)

                successful_step = True

                # Mount the file system
                cmd = "mount /dev/mmcblk0p2 /tmp/sdcard_fs"
                ssh.exec_command(cmd)

                ftp = ssh.open_sftp()
                logger.info(ftp)
                if "authorized_keys" not in ftp.listdir("/tmp/sdcard_fs/root/.ssh"):
                    successful_step = False

                # Unmount the file system
                cmd = "umount /tmp/sdcard_fs"
                ssh.exec_command(cmd)

                # Update the deployment
                if successful_step:
                    deployment.deploy_public_key()
                    db.session.add(deployment)
                    db.session.commit()

                    logger.info(f"deployment {deployment.id}: 'collected_partition_uuid' => 'public_key_deployed'")

            except (BadHostKeyException, AuthenticationException,
                    SSHException, socket.error) as e:
                logger.info(e)
                logger.info("Could not connect to %s" % server.get("ip"))
        db.session.remove()


@ignore_failed_lock_acquisition
@celery.task()
def prepare_sdcard_boot():
    logger.debug("Checking deployments in 'public_key_deployed' state")

    # Use lock in context
    with RedLock("lock/deployments/public_key_deployed"):
        pending_deployments = Deployment.query.filter_by(state="public_key_deployed").all()
        logger.debug(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(server.get("ip"), username="root", timeout=1.0)
                logger.info("Could connect to %s" % server.get("ip"))

                # Ensure 'sdcard_boot' exists
                ssh.exec_command("mkdir -p /tmp/sdcard_boot")

                # Unmount the boot partition of the SD CARD
                cmd = "umount /tmp/sdcard_boot"
                ssh.exec_command(cmd)

                # Mount the boot partition of the SD CARD
                cmd = "mount /dev/mmcblk0p1 /tmp/sdcard_boot"
                ssh.exec_command(cmd)

                # Sleep 2 seconds
                time.sleep(2)

                # Short circuit the bootcode.bin file on the SD CARD
                ftp = ssh.open_sftp()
                logger.info(ftp)
                if "bootcode.bin" in ftp.listdir("/tmp/sdcard_boot"):
                    ssh.exec_command("mv /tmp/sdcard_boot/bootcode.bin /tmp/sdcard_boot/_bootcode.bin")

                # Get the partition UUID of the rootfs partition
                (stdin, stdout, stderr) = ssh.exec_command(
                    """blkid | grep '/dev/mmcblk0p2: LABEL="rootfs"' | sed 's/.*PARTUUID=//g' | sed 's/"//g'""")
                partition_uuid = stdout.readlines()[0].strip()

                # Modify the boot PXE configuration file to mount its file system via NFS
                tftpboot_node_folder = "/tftpboot/%s" % server.get("id")
                text_file = open("%s/cmdline.txt" % tftpboot_node_folder, "w")
                text_file.write(get_sdcard_boot_cmdline() % {"partition_uuid": partition_uuid})
                text_file.close()

                # # Update the files that are going to be server via tftp
                # logger.info(f"Updating files in {tftpboot_node_folder}")
                # local_cmd = f"rsync -v -r root@{server.get('ip')}:/tmp/sdcard_boot/* {tftpboot_node_folder}/"
                # os.system(local_cmd)

                # Unmount the boot partition of the SD CARD
                cmd = "umount /tmp/sdcard_boot"
                ssh.exec_command(cmd)

                # Update the deployment
                deployment.prepare_sdcard_boot()
                db.session.add(deployment)
                db.session.commit()

                logger.info(f"deployment {deployment.id}: 'public_key_deployed' => 'configured_sdcard_boot'")

            except (BadHostKeyException, AuthenticationException,
                    SSHException, socket.error) as e:
                logger.info(e)
                logger.info("Could not connect to %s" % server.get("ip"))
        db.session.remove()


@ignore_failed_lock_acquisition
@celery.task()
def init_reboot_sdcard():
    logger.debug("Checking deployments in 'configured_sdcard_boot' state")

    # Use lock in context
    with RedLock("lock/deployments/configured_sdcard_boot"):
        pending_deployments = Deployment.query.filter_by(state="configured_sdcard_boot").all()
        logger.debug(len(pending_deployments))

        for deployment in pending_deployments:
            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            # Turn off port
            turn_off_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))

            # Wait 2 seconds
            time.sleep(2)

            # Turn on port
            turn_on_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))

            # Update the deployment
            deployment.init_reboot_sdcard()
            db.session.add(deployment)
            db.session.commit()

            logger.info(f"deployment {deployment.id}: 'configured_sdcard_boot' => 'sdcard_rebooting'")
        db.session.remove()


@ignore_failed_lock_acquisition
@celery.task()
def conclude_reboot_sdcard():
    logger.debug("Checking deployments in 'sdcard_rebooting' state")

    # Use lock in context
    with RedLock("lock/deployments/sdcard_rebooting"):
        pending_deployments = Deployment.query.filter_by(state="sdcard_rebooting").all()
        logger.debug(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            logger.info(server)

            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(server.get("ip"), username="root", timeout=1.0)
                logger.info("Could connect to %s" % server.get("ip"))

                # Update the deployment
                deployment.conclude_reboot_sdcard()
                db.session.add(deployment)
                db.session.commit()

            except (BadHostKeyException, AuthenticationException,
                    SSHException, socket.error) as e:
                logger.info(e)
                logger.info("Could not connect to %s" % server.get("ip"))

                logger.info(f"deployment {deployment.id}: 'sdcard_rebooting' => 'sdcard_rebooted'")
        db.session.remove()


@ignore_failed_lock_acquisition
@celery.task()
def finish_deployment():
    logger.debug("Checking deployments in 'sdcard_rebooted' state")

    # Use lock in context
    with RedLock("lock/deployments/sdcard_rebooted"):
        pending_deployments = Deployment.query.filter_by(state="sdcard_rebooted").all()
        logger.debug(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
            environment = [environment for environment in CLUSTER_CONFIG.get("environments") if
                           environment.get("name") == deployment.environment][0]

            # By default the deployment should be concluded
            finish_deployment = True

            # If the environment provides a function to check that
            # a service must be started before concluding the deployment
            # then the result of the function will be used
            if "ready" in environment:
                finish_deployment = environment.get("ready")(server)

            if finish_deployment:
                deployment.finish_deployment()
                db.session.add(deployment)
                db.session.commit()

                logger.info(f"deployment {deployment.id}: 'sdcard_rebooted' => 'deployed'")
        db.session.remove()


@ignore_failed_lock_acquisition
@celery.task()
def process_destruction():
    logger.debug("Checking deployments in 'destruction_requested' state")

    # Use lock in context
    with RedLock("lock/deployments/destruction_requested"):
        pending_deployments = Deployment.query.filter_by(state="destruction_requested").all()
        logger.debug(len(pending_deployments))

        for deployment in pending_deployments:
            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            # Turn off port
            turn_off_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))

            logger.info(f"deployment {deployment.id}: '{deployment.state}' => 'destroying'")

            deployment.process_destruction()
            db.session.add(deployment)
            db.session.commit()
        db.session.remove()


@ignore_failed_lock_acquisition
@celery.task()
def conclude_destruction():
    logger.debug("Checking deployments in 'destroying' state")

    # Use lock in context
    with RedLock("lock/deployments/destroying"):
        pending_deployments = Deployment.query.filter_by(state="destroying").all()
        logger.debug(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            can_connect = True
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(server.get("ip"), username="root", timeout=1.0)
                logger.info("Could connect to %s" % server.get("ip"))
            except (BadHostKeyException, AuthenticationException,
                    SSHException, socket.error) as e:
                can_connect = False

            if not can_connect:
                deployment.conclude_destruction()
                db.session.add(deployment)
                db.session.commit()

                logger.info(f"deployment {deployment.id}: 'destroying' => 'destroyed'")
        db.session.remove()
