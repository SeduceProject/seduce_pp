import celery
from database import db
from database import Deployment
import subprocess
from lib.config.cluster_config import CLUSTER_CONFIG
from redlock import RedLock
import os
import shutil
from lib.dgs121028p import acquire_gambit, get_ports_status, turn_on_port, turn_off_port
import time
import paramiko
from paramiko.ssh_exception import BadHostKeyException, AuthenticationException, SSHException
import socket
import re


NFS_BOOT_CMD_LINE = """dwc_otg.lpm_enable=0 console=serial0,115200 console=tty1 root=/dev/nfs nfsroot=192.168.1.17:/nfs/raspi1,udp,v3 rw ip=dhcp rootwait elevator=deadline rootfstype=nfs"""
# SDCARD_RESIZE_BOOT_CMD_LINE = """dwc_otg.lpm_enable=0 console=serial0,115200 console=tty1 root=PARTUUID=%(partition_uuid)s rootfstype=ext4 elevator=deadline fsck.repair=yes rootwait quiet init=/usr/lib/raspi-config/init_resize.sh"""
SDCARD_RESIZE_BOOT_CMD_LINE = """dwc_otg.lpm_enable=0 console=serial0,115200 console=tty1 root=/dev/mmcblk0p2 rootfstype=ext4 elevator=deadline fsck.repair=yes rootwait quiet init=/usr/lib/raspi-config/init_resize.sh"""
SDCARD_BOOT_CMD_LINE = """dwc_otg.lpm_enable=0 console=serial0,115200 console=tty1 root=PARTUUID=%(partition_uuid)s rootfstype=ext4 elevator=deadline fsck.repair=yes rootwait"""

SERVER_PUBLIC_KEY = """ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDDjXBuWj8MJuGcJDx1/ch7nDBptyoXjBP3DNQPel+A+sI/76dT/MPw6HgUxywb0aJ1L50QU0xDU/dhl0er4WK31DLf6QR2ursZ7yYhgrRm8uugYEIYxs8qu5SyNXiNPOTnH+Pd+IUt/T3iqyrPLOifnuqWaeN26WqUlWiAcqIrJdfl+KgNuYOS4u3bFNEPBuab3wqi8JREkv25j9NJ7UMrVUzhQ8eMeCQmQsoVBsMwfhLZ/DyZz4o/+IsP05AmJs0q3eJJwsFSWerZTNtes97qkD/H+RQv5VhGqYKncyCoFHt0D4lstFizlG/1rxow6scssQR2dfs1XSuc6VHCnuLv root@nuc1"""

@celery.task()
def prepare_nfs_boot():
    print("Checking deployments in 'created' state")

    # Use lock in context
    with RedLock("lock/deployments/created"):
        pending_deployments = Deployment.query.filter_by(state="created").all()
        print(len(pending_deployments))

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
            text_file.write(NFS_BOOT_CMD_LINE)
            text_file.close()

            # Update the deployment
            deployment.prepare_nfs_boot()
            db.session.add(deployment)
            db.session.commit()


@celery.task()
def init_reboot_nfs():
    print("Checking deployments in 'configured_nfs_boot' state")

    # Use lock in context
    with RedLock("lock/deployments/configured_nfs_boot"):
        pending_deployments = Deployment.query.filter_by(state="configured_nfs_boot").all()
        print(len(pending_deployments))

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


@celery.task()
def conclude_reboot_nfs():
    print("Checking deployments in 'nfs_rebooting' state")

    # Use lock in context
    with RedLock("lock/deployments/nfs_rebooting"):
        pending_deployments = Deployment.query.filter_by(state="nfs_rebooting").all()
        print(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            print(server)

            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(server.get("ip"), username="root", timeout=1.0)
                print("Could connect to %s" % server.get("ip"))

                # Update the deployment
                deployment.conclude_reboot_nfs()
                db.session.add(deployment)
                db.session.commit()

            except (BadHostKeyException, AuthenticationException,
                    SSHException, socket.error) as e:
                print(e)
                print("Could not connect to %s" % server.get("ip"))


@celery.task()
def prepare_deployment():
    print("Checking deployments in 'nfs_rebooted' state")

    # Use lock in context
    with RedLock("lock/deployments/nfs_rebooted"):
        pending_deployments = Deployment.query.filter_by(state="nfs_rebooted").all()
        print(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            print(server)

            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(server.get("ip"), username="root")
                print("Could connect to %s" % server.get("ip"))

                # Create folder for mounting the sd card
                ssh.exec_command("mkdir -p /mnt/sdcard_boot")
                ssh.exec_command("mkdir -p /mnt/sdcard_fs")

                # Update the deployment
                deployment.prepared_deployment()
                db.session.add(deployment)
                db.session.commit()

            except (BadHostKeyException, AuthenticationException,
                    SSHException, socket.error) as e:
                print(e)
                print("Could not connect to %s" % server.get("ip"))


@celery.task()
def deploy_env():
    print("Checking deployments in 'ready_deploy' state")

    # Use lock in context
    with RedLock("lock/deployments/ready_deploy"):
        pending_deployments = Deployment.query.filter_by(state="ready_deploy").all()
        print(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            print(server)

            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(server.get("ip"), username="root", timeout=1.0)
                print("Could connect to %s" % server.get("ip"))

                # Write the image of the environment on SD card
                deploy_cmd = """rm /tmp/deployment_done; unzip -p /environments/2018-11-13-raspbian-stretch-lite.zip | sudo dd of=/dev/mmcblk0 bs=4M conv=fsync status=progress 2>&1 | tee /tmp/progress.txt; touch /tmp/deployment_done;"""
                screen_deploy_cmd = "screen -d -m bash -c '%s'" % deploy_cmd
                ssh.exec_command(screen_deploy_cmd)

                # Update the deployment
                deployment.deploy_env()
                db.session.add(deployment)
                db.session.commit()

            except (BadHostKeyException, AuthenticationException,
                    SSHException, socket.error) as e:
                print(e)
                print("Could not connect to %s" % server.get("ip"))


@celery.task()
def deploy_env_finished():
    print("Checking deployments in 'environment_deploying' state")

    # Use lock in context
    with RedLock("lock/deployments/environment_deploying"):
        pending_deployments = Deployment.query.filter_by(state="environment_deploying").all()
        print(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            print(server)

            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(server.get("ip"), username="root", timeout=1.0)
                print("Could connect to %s" % server.get("ip"))

                # Write the image of the environment on SD card
                ftp = ssh.open_sftp()
                print(ftp)

                if "deployment_done" in ftp.listdir("/tmp"):
                    # Update the deployment
                    deployment.deploy_env_finished()
                else:
                    # Get the progress
                    if "progress.txt" in ftp.listdir("/tmp"):
                        cmd = """cat /tmp/progress.txt"""
                        (stdin, stdout, stderr) = ssh.exec_command(cmd)
                        lines = stdout.readlines()
                        output = "" if len(lines) == 0 else lines[-1].split("\r")[-1]
                        deployment.label = output

                db.session.add(deployment)
                db.session.commit()

            except (BadHostKeyException, AuthenticationException,
                    SSHException, socket.error) as e:
                print(e)
                print("Could not connect to %s" % server.get("ip"))


@celery.task()
def configure_sdcard_resize_boot():
    print("Checking deployments in 'environment_deployed' state")

    # Use lock in context
    with RedLock("lock/deployments/environment_deployed"):
        pending_deployments = Deployment.query.filter_by(state="environment_deployed").all()
        print(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(server.get("ip"), username="root", timeout=1.0)
                print("Could connect to %s" % server.get("ip"))

                # Ensure 'sdcard_boot' and 'sdcard_fs' exists
                ssh.exec_command("mkdir -p /mnt/sdcard_boot")
                ssh.exec_command("mkdir -p /mnt/sdcard_fs")

                # Unmount the boot file system
                cmd = "umount /mnt/sdcard_boot"
                ssh.exec_command(cmd)

                # Unmount the root file system
                cmd = "umount /mnt/sdcard_fs"
                ssh.exec_command(cmd)

                # Mount the boot partition of the SD CARD
                cmd = "mount /dev/mmcblk0p1 /mnt/sdcard_boot"
                ssh.exec_command(cmd)

                # Mount the root partition of the SD CARD
                cmd = "mount /dev/mmcblk0p2 /mnt/sdcard_fs"
                ssh.exec_command(cmd)

                # Wait 2 second
                time.sleep(2)

                # Short circuit the bootcode.bin file on the SD CARD
                ftp = ssh.open_sftp()
                print(ftp)
                if "bootcode.bin" in ftp.listdir("/mnt/sdcard_boot"):
                    ssh.exec_command("mv /mnt/sdcard_boot/bootcode.bin /mnt/sdcard_boot/_bootcode.bin")

                # Create a ssh file on the SD Card
                cmd = "echo '1' > /mnt/sdcard_boot/ssh"
                ssh.exec_command(cmd)

                # Tweak: make sure that the ssh service will be enabled whenever /boot/ssh has been create
                cmd = "sed -i 's/ConditionPathExistsGlob.*//g' /mnt/sdcard_fs/etc/systemd/system/multi-user.target.wants/sshswitch.service"
                ssh.exec_command(cmd)

                # Unmount the boot partition of the SD CARD
                cmd = "umount /mnt/sdcard_boot"
                ssh.exec_command(cmd)

                cmd = "umount /mnt/sdcard_fs"
                ssh.exec_command(cmd)

                # Modify the boot PXE configuration file to resize the FS
                tftpboot_node_folder = "/tftpboot/%s" % server.get("id")
                text_file = open("%s/cmdline.txt" % tftpboot_node_folder, "w")
                text_file.write(SDCARD_RESIZE_BOOT_CMD_LINE)
                text_file.close()

                # /!\ here we check that changes have been committed to the SD card

                # Mount the boot partition of the SD CARD
                cmd = "mount /dev/mmcblk0p1 /mnt/sdcard_boot"
                ssh.exec_command(cmd)

                # Wait 2 second
                time.sleep(2)

                successful_step = True

                if "_bootcode.bin" not in ftp.listdir("/mnt/sdcard_boot"):
                    print("bootcode.bin file has not been renamed!")
                    successful_step = False

                if "ssh" not in ftp.listdir("/mnt/sdcard_boot"):
                    print("ssh file has not been created!")
                    successful_step = False

                # Unmount the boot partition of the SD CARD
                cmd = "umount /mnt/sdcard_boot"
                ssh.exec_command(cmd)

                # Update the deployment
                if successful_step:
                    deployment.configure_sdcard_resize_boot()
                    db.session.add(deployment)
                    db.session.commit()

            except (BadHostKeyException, AuthenticationException,
                    SSHException, socket.error) as e:
                print(e)
                print("Could not connect to %s" % server.get("ip"))


@celery.task()
def init_reboot_nfs_after_resize():
    print("Checking configured_nfs_boot in 'configured_sdcard_resize_boot' state")

    # Use lock in context
    with RedLock("lock/deployments/configured_sdcard_resize_boot"):
        pending_deployments = Deployment.query.filter_by(state="configured_sdcard_resize_boot").all()
        print(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            # Turn off port
            turn_off_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))

            # Wait 2 seconds
            time.sleep(2)

            # Turn on port
            turn_on_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))

            # Wait 40 seconds to let the FS to resize
            time.sleep(40)

            # Modify the boot PXE configuration file to resize the FS
            tftpboot_node_folder = "/tftpboot/%s" % server.get("id")
            text_file = open("%s/cmdline.txt" % tftpboot_node_folder, "w")
            text_file.write(NFS_BOOT_CMD_LINE)
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


@celery.task()
def conclude_reboot_nfs_after_resize():
    print("Checking deployments in 'nfs_rebooting_after_resize' state")

    # Use lock in context
    with RedLock("lock/deployments/nfs_rebooting_after_resize"):
        pending_deployments = Deployment.query.filter_by(state="nfs_rebooting_after_resize").all()
        print(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            print(server)

            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(server.get("ip"), username="root", timeout=1.0)
                print("Could connect to %s" % server.get("ip"))

                # Update the deployment
                deployment.conclude_reboot_nfs_after_resize()
                db.session.add(deployment)
                db.session.commit()

            except (BadHostKeyException, AuthenticationException,
                    SSHException, socket.error) as e:
                print(e)
                print("Could not connect to %s" % server.get("ip"))


@celery.task()
def collect_partition_uuid():
    print("Checking deployments in 'nfs_rebooted_after_resize' state")

    # Use lock in context
    with RedLock("lock/deployments/nfs_rebooted_after_resize"):
        pending_deployments = Deployment.query.filter_by(state="nfs_rebooted_after_resize").all()
        print(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(server.get("ip"), username="root", timeout=1.0)
                print("Could connect to %s" % server.get("ip"))

                successful_step = True

                # Ensure 'sdcard_boot' exists
                ssh.exec_command("mkdir -p /mnt/sdcard_boot")

                # Unmount the boot file system
                cmd = "umount /mnt/sdcard_fs"
                ssh.exec_command(cmd)

                # Mount the boot partition of the SD CARD
                cmd = "mount /dev/mmcblk0p2 /mnt/sdcard_fs"
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
                cmd = "umount /mnt/sdcard_boot"
                ssh.exec_command(cmd)

                # Update the deployment
                if successful_step:
                    deployment.collect_partition_uuid()
                else:
                    deployment.retry_resize()

                db.session.add(deployment)
                db.session.commit()

            except (BadHostKeyException, AuthenticationException,
                    SSHException, socket.error) as e:
                print(e)
                print("Could not connect to %s" % server.get("ip"))


@celery.task()
def deploy_public_key():
    print("Checking deployments in 'collected_partition_uuid' state")

    # Use lock in context
    with RedLock("lock/deployments/collected_partition_uuid"):
        pending_deployments = Deployment.query.filter_by(state="collected_partition_uuid").all()
        print(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(server.get("ip"), username="root", timeout=1.0)
                print("Could connect to %s" % server.get("ip"))

                # Unmount the file system
                cmd = "umount /mnt/sdcard_fs"
                ssh.exec_command(cmd)

                # Mount the file system of the SD CARD
                cmd = "mount /dev/mmcblk0p2 /mnt/sdcard_fs"
                ssh.exec_command(cmd)

                # Sleep 2 seconds
                time.sleep(2)

                # Create a ssh folder in the root folder of the SD CARD's file system
                cmd = "mkdir -p /mnt/sdcard_fs/root/.ssh"
                ssh.exec_command(cmd)

                # Add the public key of the server
                cmd = "cp /root/.ssh/authorized_keys /mnt/sdcard_fs/root/.ssh/authorized_keys"
                ssh.exec_command(cmd)

                # Sleep 2 seconds
                time.sleep(2)

                # Add the public key of the server (second try)
                cmd = "echo '\n%s' >> /mnt/sdcard_fs/root/.ssh/authorized_keys" % SERVER_PUBLIC_KEY
                ssh.exec_command(cmd)

                # Add the public key of the user
                cmd = "echo '\n%s' >> /mnt/sdcard_fs/root/.ssh/authorized_keys" % deployment.public_key
                ssh.exec_command(cmd)

                successful_step = True

                ftp = ssh.open_sftp()
                print(ftp)
                if "authorized_keys" not in ftp.listdir("/mnt/sdcard_fs/root/.ssh"):
                    successful_step = False

                # Unmount the file system
                cmd = "umount /mnt/sdcard_fs"
                ssh.exec_command(cmd)

                # Update the deployment
                if successful_step:
                    deployment.deploy_public_key()
                    db.session.add(deployment)
                    db.session.commit()

            except (BadHostKeyException, AuthenticationException,
                    SSHException, socket.error) as e:
                print(e)
                print("Could not connect to %s" % server.get("ip"))


@celery.task()
def prepare_sdcard_boot():
    print("Checking deployments in 'public_key_deployed' state")

    # Use lock in context
    with RedLock("lock/deployments/public_key_deployed"):
        pending_deployments = Deployment.query.filter_by(state="public_key_deployed").all()
        print(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(server.get("ip"), username="root", timeout=1.0)
                print("Could connect to %s" % server.get("ip"))

                # Ensure 'sdcard_boot' exists
                ssh.exec_command("mkdir -p /mnt/sdcard_boot")

                # Unmount the boot partition of the SD CARD
                cmd = "umount /mnt/sdcard_boot"
                ssh.exec_command(cmd)

                # Mount the boot partition of the SD CARD
                cmd = "mount /dev/mmcblk0p1 /mnt/sdcard_boot"
                ssh.exec_command(cmd)

                # Sleep 2 seconds
                time.sleep(2)

                # Short circuit the bootcode.bin file on the SD CARD
                ftp = ssh.open_sftp()
                print(ftp)
                if "bootcode.bin" in ftp.listdir("/mnt/sdcard_boot"):
                    ssh.exec_command("mv /mnt/sdcard_boot/bootcode.bin /mnt/sdcard_boot/_bootcode.bin")

                # Get the partition UUID of the rootfs partition
                (stdin, stdout, stderr) = ssh.exec_command(
                    """blkid | grep '/dev/mmcblk0p2: LABEL="rootfs"' | sed 's/.*PARTUUID=//g' | sed 's/"//g'""")
                partition_uuid = stdout.readlines()[0].strip()

                # Modify the boot PXE configuration file to mount its file system via NFS
                tftpboot_node_folder = "/tftpboot/%s" % server.get("id")
                text_file = open("%s/cmdline.txt" % tftpboot_node_folder, "w")
                text_file.write(SDCARD_BOOT_CMD_LINE % {"partition_uuid": partition_uuid})
                text_file.close()

                # Unmount the boot partition of the SD CARD
                cmd = "umount /mnt/sdcard_boot"
                ssh.exec_command(cmd)

                # Update the deployment
                deployment.prepare_sdcard_boot()
                db.session.add(deployment)
                db.session.commit()

            except (BadHostKeyException, AuthenticationException,
                    SSHException, socket.error) as e:
                print(e)
                print("Could not connect to %s" % server.get("ip"))


@celery.task()
def init_reboot_sdcard():
    print("Checking deployments in 'configured_sdcard_boot' state")

    # Use lock in context
    with RedLock("lock/deployments/configured_sdcard_boot"):
        pending_deployments = Deployment.query.filter_by(state="configured_sdcard_boot").all()
        print(len(pending_deployments))

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


@celery.task()
def conclude_reboot_sdcard():
    print("Checking deployments in 'sdcard_rebooting' state")

    # Use lock in context
    with RedLock("lock/deployments/sdcard_rebooting"):
        pending_deployments = Deployment.query.filter_by(state="sdcard_rebooting").all()
        print(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            print(server)

            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(server.get("ip"), username="root", timeout=1.0)
                print("Could connect to %s" % server.get("ip"))

                # Update the deployment
                deployment.conclude_reboot_sdcard()
                db.session.add(deployment)
                db.session.commit()

            except (BadHostKeyException, AuthenticationException,
                    SSHException, socket.error) as e:
                print(e)
                print("Could not connect to %s" % server.get("ip"))


@celery.task()
def finish_deployment():
    print("Checking deployments in 'sdcard_rebooted' state")

    # Use lock in context
    with RedLock("lock/deployments/sdcard_rebooted"):
        pending_deployments = Deployment.query.filter_by(state="sdcard_rebooted").all()
        print(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            deployment.finish_deployment()
            db.session.add(deployment)
            db.session.commit()


@celery.task()
def process_destruction():
    print("Checking deployments in 'destruction_requested' state")

    # Use lock in context
    with RedLock("lock/deployments/destruction_requested"):
        pending_deployments = Deployment.query.filter_by(state="destruction_requested").all()
        print(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            # Turn off port
            turn_off_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))

            deployment.process_destruction()
            db.session.add(deployment)
            db.session.commit()


@celery.task()
def conclude_destruction():
    print("Checking deployments in 'destroying' state")

    # Use lock in context
    with RedLock("lock/deployments/destroying"):
        pending_deployments = Deployment.query.filter_by(state="destroying").all()
        print(len(pending_deployments))

        for deployment in pending_deployments:

            # Get description of the server that will be deployed
            server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]

            can_connect = True
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(server.get("ip"), username="root", timeout=1.0)
                print("Could connect to %s" % server.get("ip"))
            except (BadHostKeyException, AuthenticationException,
                    SSHException, socket.error) as e:
                can_connect = False

            if not can_connect:
                deployment.conclude_destruction()
                db.session.add(deployment)
                db.session.commit()
