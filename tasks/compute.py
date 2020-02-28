import celery, datetime, logging, os, paramiko, re, random, shutil, socket, subprocess, sys, time, traceback, uuid
from database import db, Deployment
from lib.config.cluster_config import CLUSTER_CONFIG
from lib.deployment import get_nfs_boot_cmdline, get_sdcard_boot_cmdline, get_sdcard_resize_boot_cmdline
from lib.dgs121028p import turn_on_port, turn_off_port
from paramiko.ssh_exception import BadHostKeyException, AuthenticationException, SSHException
from redlock import RedLock
from sqlalchemy import or_


def collect_nodes(process, node_state):
    try:
        logger_compute = logging.getLogger("COMPUTE")
        pending_deployments = Deployment.query.filter_by(state=node_state).all()
        if len(pending_deployments) > 0:
            for d in pending_deployments:
                if d.updated_at is not None:
                    last_update = datetime.datetime.strptime(str(d.updated_at), '%Y-%m-%d %H:%M:%S')
                else:
                    last_update = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                logger_compute.info("### Node '%s' enters in '%s' state at %s" %
                        (d.server_id, node_state, last_update))
            with RedLock("lock/deployments/%s" % node_state):
                process(pending_deployments, logger_compute)
        db.session.remove()
    except Exception:
        logger_compute.exception("Exception in '%s' state:" % node_state)


def is_file_ssh(ssh_session, path_file):
    try:
        (stdin, stdout, stderr) = ssh_session.exec_command("cat %s | wc -l" % path_file)
        output = stdout.readlines()
        return int(output[0].strip())
    except SSHException:
        return -1


def md5sum_ssh(ssh_session, path_file):
    try:
        (stdin, stdout, stderr) = ssh_session.exec_command("md5sum %s | cut -d ' ' -f1" % path_file)
        output = stdout.readlines()
        return output[0].strip()
    except SSHException:
        return "error"


def ps_ssh(ssh_session, bash_cmd):
    try:
        (stdin, stdout, stderr) = ssh_session.exec_command("ps aux | grep %s | grep -v grep | wc -l" % bash_cmd)
        output = stdout.readlines()
        return int(output[0].strip())
    except SSHException:
        return -1


def nfs_boot_conf_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        # Create a folder containing network boot files that will be served via TFTP
        # tftpboot_template_folder = "/tftpboot/rpiboot"
        tftpboot_template_folder = "/tftpboot/rpiboot_uboot"
        tftpboot_node_folder = "/tftpboot/%s" % server.get("id")
        if os.path.isdir(tftpboot_node_folder):
            shutil.rmtree(tftpboot_node_folder)
        shutil.copytree(tftpboot_template_folder, tftpboot_node_folder)
        # Modify the boot PXE configuration file to mount its file system via NFS
        text_file = open("%s/cmdline.txt" % tftpboot_node_folder, "w")
        text_file.write(get_nfs_boot_cmdline() % {"controller_ip": CLUSTER_CONFIG.get("controller").get("ip")})
        text_file.close()
        # Update the deployment
        deployment.nfs_boot_conf_fct()
        deployment.updated_at = datetime.datetime.utcnow()
        db.session.add(deployment)
        db.session.commit()


def nfs_boot_off_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        # Turn off port
        turn_off_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
        # Update the deployment
        deployment.nfs_boot_off_fct()
        deployment.updated_at = datetime.datetime.utcnow()
        db.session.add(deployment)
        db.session.commit()


def nfs_boot_on_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        # Turn on port
        turn_on_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
        # Update the deployment
        deployment.nfs_boot_on_fct()
        deployment.updated_at = datetime.datetime.utcnow()
        db.session.add(deployment)
        db.session.commit()


def env_copy_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            # Get the path to the IMG file
            environment = [environment for environment in CLUSTER_CONFIG.get("environments")
                    if environment.get("name") == deployment.environment][0]
            environment_img_path = environment.get("img_path")
            logger.info("%s: copy %s to the SDCARD" % (server.get("id"), environment_img_path))
            # Write the image of the environment on SD card
            # rsh pipi@192.168.122.236 "cat 500MB.img" | pv -n -p -s 524m 2> /tmp/progress_{server['id']}.txt | dd of=/dev/mmcblk0 conv=fsync bs=4M
            deploy_cmd = f"""rm -f /tmp/done_{server['id']}.txt; rsh -o "StrictHostKeyChecking no" %s@%s "cat {environment_img_path}" | dd of=/dev/mmcblk0 bs=4M conv=fsync; touch /tmp/done_{server['id']}.txt;""" % (CLUSTER_CONFIG.get("controller").get("user"), CLUSTER_CONFIG.get("controller").get("ip"))
            ssh.exec_command(deploy_cmd)
            # Update the deployment
            deployment.env_copy_fct()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
            ssh.close()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            logger.warning("Could not connect to %s" % server.get("ip"))


def env_check_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            # Write the image of the environment on SD card
            ftp = ssh.open_sftp()
            logger.info(f"Looking for done_{server['id']}.txt")
            if f"done_{server['id']}.txt" in ftp.listdir("/tmp"):
                # Update the deployment
                deployment.env_check_fct()
                deployment.updated_at = datetime.datetime.utcnow()
                db.session.add(deployment)
                db.session.commit()
            ssh.close()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            logger.warning("Could not connect to %s" % server.get("ip"))


def fs_mount_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            # Mount the boot partition of the SD CARD
            cmd = "partprobe; mount /dev/mmcblk0p1 /mnt/sdcard_boot; mount /dev/mmcblk0p2 /mnt/sdcard_fs"
            ssh.exec_command(cmd)
            (stdin, stdout, stderr) = ssh.exec_command("mount -f | grep mmcblk0 | wc -l")
            output = stdout.readlines()
            nb_mount = int(output[0].strip())
            if nb_mount == 2:
                # Update the deployment
                if deployment.environment == "tiny_core":
                    deployment.fs_mount_fct2()
                else:
                    deployment.fs_mount_fct()
                deployment.updated_at = datetime.datetime.utcnow()
                db.session.add(deployment)
                db.session.commit()
            else:
                logger.warning("%s: Wrong number of mounted partitions. %d detected partition(s)" %
                        (server.get("id"), nb_mount))
            ssh.close()
        except (BadHostKeyException, AuthenticationException, SHException, socket.error) as e:
            logger.warning("Could not connect to %s" % server.get("ip"))


def fs_conf_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            # Short circuit the bootcode.bin file on the SD CARD
            ssh.exec_command("rm /mnt/sdcard_boot/bootcode.bin")
            # Create a ssh file on the SD Card
            cmd = "echo '1' > /mnt/sdcard_boot/ssh"
            ssh.exec_command(cmd)
            # Create a folder containing network boot files that will be served via TFTP
            tftpboot_template_folder = "/tftpboot/rpiboot"
            # tftpboot_template_folder = "/tftpboot/rpiboot_uboot"
            tftpboot_node_folder = "/tftpboot/%s" % server.get("id")
            if os.path.isdir(tftpboot_node_folder):
                shutil.rmtree(tftpboot_node_folder)
            shutil.copytree(tftpboot_template_folder, tftpboot_node_folder)
            # Modify the boot PXE configuration file to resize the FS
            tftpboot_node_folder = "/tftpboot/%s" % server.get("id")
            text_file = open("%s/cmdline.txt" % tftpboot_node_folder, "w")
            text_file.write(get_sdcard_resize_boot_cmdline())
            text_file.close()
            # Update the deployment
            deployment.fs_conf_fct()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
            ssh.close()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            logger.warning("Could not connect to %s" % server.get("ip"))


def fs_check_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            ftp = ssh.open_sftp()
            successful_step = True
            if "bootcode.bin" in ftp.listdir("/mnt/sdcard_boot"):
                logger.error("bootcode.bin file has not been removed!")
                successful_step = False
            if "ssh" not in ftp.listdir("/mnt/sdcard_boot"):
                logger.error("ssh file has not been created!")
                successful_step = False
            # Update the deployment
            if successful_step:
                deployment.fs_check_fct()
                deployment.updated_at = datetime.datetime.utcnow()
                db.session.add(deployment)
                db.session.commit()
            ssh.close()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            logger.warning("Could not connect to %s" % server.get("ip"))


def resize_off_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        # Turn off port
        turn_off_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
        # Update the deployment state
        deployment.resize_off_fct()
        deployment.updated_at = datetime.datetime.utcnow()
        db.session.add(deployment)
        db.session.commit()


def resize_on_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        # Turn on port
        turn_on_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
        # Update the deployment state
        deployment.resize_on_fct()
        deployment.updated_at = datetime.datetime.utcnow()
        db.session.add(deployment)
        db.session.commit()


def resize_inprogress_fct(deployments, logger):
    for deployment in deployments:
        updated = datetime.datetime.strptime(str(deployment.updated_at), '%Y-%m-%d %H:%M:%S')
        elapsedTime = (datetime.datetime.utcnow() - updated).total_seconds()
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        if elapsedTime >= 40:
            # Modify the boot PXE configuration file to resize the FS
            tftpboot_node_folder = "/tftpboot/%s" % server.get("id")
            text_file = open("%s/cmdline.txt" % tftpboot_node_folder, "w")
            text_file.write(get_nfs_boot_cmdline() % {"controller_ip": CLUSTER_CONFIG.get("controller").get("ip")})
            text_file.close()
            # Turn off port
            turn_off_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
            deployment.resize_inprogress_fct()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
        else:
            logger.info("Waiting %s: %d/40s" % (server.get("ip"), elapsedTime))


def resize_done_fct(deployments, logger):
    for deployment in deployments:
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        # Turn on port
        turn_on_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
        deployment.resize_done_fct()
        deployment.updated_at = datetime.datetime.utcnow()
        db.session.add(deployment)
        db.session.commit()


def resize_check_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            successful_step = True
            # Check the size of the partition : if it is small, go back to 'environment_deployed' state
            cmd = """lsblk | grep mmcblk0p2 | awk '{print $4}' | sed 's/G//g'"""
            (stdin, stdout, stderr) = ssh.exec_command(cmd)
            output = stdout.readlines()
            partition_size = float(output[0].strip())
            # Check if resize has been successful (partition's size should be larger than 4 GB)
            logger.info("partition_size: %f" % partition_size)
            if partition_size < 4.0:
                successful_step = False
            # Update the deployment
            if successful_step:
                deployment.resize_check_fct()
            else:
                deployment.retry_resize()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
            ssh.close()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            logger.warning("Could not connect to %s" % server.get("ip"))


def ssh_key_mount_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            # Mount the file system of the SD CARD
            cmd = "mount /dev/mmcblk0p2 /mnt/sdcard_fs"
            ssh.exec_command(cmd)
            cmd = "mount /dev/mmcblk0p1 /mnt/sdcard_boot"
            ssh.exec_command(cmd)
            deployment.ssh_key_mount_fct()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
            ssh.close()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            logger.warning("Could not connect to %s" % server.get("ip"))

def ssh_key_copy_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            # Create a ssh folder in the root folder of the SD CARD's file system
            cmd = "mkdir -p /mnt/sdcard_fs/root/.ssh"
            ssh.exec_command(cmd)
            # Add the public key of the server
            cmd = "cp /root/.ssh/authorized_keys /mnt/sdcard_fs/root/.ssh/authorized_keys && sync"
            ssh.exec_command(cmd)
            deployment.ssh_key_copy_fct()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
            ssh.close()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            logging.warning("Could not connect to %s" % server.get("ip"))


def ssh_key_user_fct(deployments, logger):
    for deployment in deployments:
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            # Secure the cloud9 connection
            if deployment.environment == 'raspbian_cloud9':
                cmd = "echo '#!/bin/sh\nnodejs /var/lib/c9sdk/server.js -l 0.0.0.0 --listen 0.0.0.0 --port 8181 -a admin:%s -w /workspace' > /mnt/sdcard_fs/usr/local/bin/c9" % deployment.c9pwd
                ssh.exec_command(cmd)
            # Start the SSH server on startup
            if deployment.environment == 'raspbian_buster':
                cmd = "chroot /mnt/sdcard_fs/ update-rc.d ssh enable"
                ssh.exec_command(cmd)
            # Add the public key of the user
            cmd = "echo '\n%s' >> /mnt/sdcard_fs/root/.ssh/authorized_keys && sync && umount /mnt/sdcard_fs" % deployment.public_key
            ssh.exec_command(cmd)
            # Update the deployment
            deployment.ssh_key_user_fct()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            logger.warning("Could not connect to %s" % server.get("ip"))


def fs_boot_conf_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            # Get the partition UUID of the rootfs partition
            (stdin, stdout, stderr) = ssh.exec_command(
                """blkid | grep '/dev/mmcblk0p2: LABEL="rootfs"' | sed 's/.*PARTUUID=//g' | sed 's/"//g'""")
            partition_uuid = stdout.readlines()[0].strip()
            # Create a folder containing network boot files that will be served via TFTP
            tftpboot_template_folder = "/tftpboot/rpiboot_uboot"
            tftpboot_node_folder = "/tftpboot/%s" % server.get("id")
            if os.path.isdir(tftpboot_node_folder):
                shutil.rmtree(tftpboot_node_folder)
            shutil.copytree(tftpboot_template_folder, tftpboot_node_folder)
            cmd = f"""
                scp -o "StrictHostKeyChecking no" root@{server.get("ip")}:/mnt/sdcard_boot/kernel7.img {tftpboot_node_folder}/.
                scp -o "StrictHostKeyChecking no" -r root@{server.get("ip")}:/mnt/sdcard_boot/bcm2710-*.dtb {tftpboot_node_folder}/.
            """
            os.system(cmd)
            # Modify the boot PXE configuration file to mount its file system via NFS
            text_file = open("%s/cmdline.txt" % tftpboot_node_folder, "w")
            text_file.write(get_sdcard_boot_cmdline() % {"partition_uuid": partition_uuid})
            text_file.close()
            # Update the deployment
            deployment.fs_boot_conf_fct()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
            ssh.close()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            logger.warning("Could not connect to %s" % server.get("ip"))


def fs_boot_off_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        # Turn off port
        turn_off_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
        # Update the deployment
        deployment.fs_boot_off_fct()
        deployment.updated_at = datetime.datetime.utcnow()
        db.session.add(deployment)
        db.session.commit()

def fs_boot_on_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        # Turn on port
        turn_on_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
        # Update the deployment
        deployment.fs_boot_on_fct()
        deployment.updated_at = datetime.datetime.utcnow()
        db.session.add(deployment)
        db.session.commit()


def fs_boot_check_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            updated = datetime.datetime.strptime(str(deployment.updated_at), '%Y-%m-%d %H:%M:%S')
            elapsedTime = (datetime.datetime.utcnow() - updated).total_seconds()
            logger.info("Could connect to %s after %s seconds" % (server.get("ip"), elapsedTime))
            # Update the deployment
            deployment.fs_boot_check_fct()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
            ssh.close()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            updated = datetime.datetime.strptime(str(deployment.updated_at), '%Y-%m-%d %H:%M:%S')
            elapsedTime = (datetime.datetime.utcnow() - updated).total_seconds()
            logger.info("Could not connect to %s since %d seconds" % (server.get("ip"), elapsedTime))
            if elapsedTime > 90:
                logger.error("Retry the SSH configuration")
                # Modify the boot PXE configuration file to boot from NFS
                tftpboot_node_folder = "/tftpboot/%s" % server.get("id")
                text_file = open("%s/cmdline.txt" % tftpboot_node_folder, "w")
                text_file.write(get_nfs_boot_cmdline() % {"controller_ip": CLUSTER_CONFIG.get("controller").get("ip")})
                text_file.close()
                # Turn off port
                turn_off_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
                # Update the deployment
                deployment.fs_boot_check_fct2()
                deployment.updated_at = datetime.datetime.utcnow()
                db.session.add(deployment)
                db.session.commit()


def ssh_config_2_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        # Turn on port
        turn_on_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
        # Update the deployment
        deployment.resize_check_fct()
        deployment.updated_at = datetime.datetime.utcnow()
        db.session.add(deployment)
        db.session.commit()


def last_check_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        environment = [environment for environment in CLUSTER_CONFIG.get("environments")
                if environment.get("name") == deployment.environment][0]
        # By default the deployment should be concluded
        finish_init = True
        finish_deployment = True
        # Implement a mecanism that execute the init script
        if deployment.init_script is not None and deployment.init_script != "":
            finish_init = False
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(server.get("ip"), username=environment.get("ssh_user"), timeout=1.0)
                ftp = ssh.open_sftp()
                if "started_init_script" not in ftp.listdir("/tmp/"):
                    # Generate random title
                    random_file_name = str(uuid.uuid1())
                    random_file_path = f"/tmp/{random_file_name}"
                    with open(random_file_path, mode="w") as f:
                        f.write("DEBIAN_FRONTEND=noninteractive\n")
                        f.write(deployment.init_script)
                    ftp.put(random_file_path, "/tmp/init_script.sh")
                    if "init_script.sh" not in ftp.listdir("/tmp"):
                        logger.error(f"\"init_script.sh\" not in /tmp")
                        continue
                    # Launch init script
                    cmd = "touch /tmp/started_init_script; sed -i 's/\r$//' /tmp/init_script.sh; %s /tmp/init_script.sh; touch /tmp/finished_init_script" % environment.get("shell")
                    ssh.exec_command(cmd)
                if "finished_init_script" in ftp.listdir("/tmp/"):
                    finish_init = True
                ssh.close()
            except:
                pass
        # If the environment provides a function to check that
        # a service must be started before concluding the deployment
        # then the result of the function will be used
        if "ready" in environment:
            finish_deployment = environment.get("ready")(server, environment)
        logger.info("finish_init %s" % finish_init)
        logger.info("finish_deployment %s" % finish_deployment)
        if finish_deployment and finish_init:
            deployment.last_check_fct()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()


# Deploy tinycore system
def tc_conf_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            # Configure the SDCARD in order to reboot on it
            ssh.exec_command("rm /mnt/sdcard_boot/bootcode.bin /mnt/sdcard_fs/tce/mydata.tgz; cp /environments/mydata.tgz /mnt/sdcard_fs/tce/; sync")
            # Copy boot files to the tftp folder
            tftpboot_node_folder = "/tftpboot/%s" % server.get("id")
            cmd = f"scp -o 'StrictHostKeyChecking no' -r root@{server.get('ip')}:/mnt/sdcard_boot/* {tftpboot_node_folder}/"
            subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Check the mydata.tgz copy
            md5sum = md5sum_ssh(ssh, "/mnt/sdcard_fs/tce/mydata.tgz")
            if md5sum == '5fe96e4822be6b1965be8de12b11916c':
                deployment.tc_conf_fct()
                deployment.updated_at = datetime.datetime.utcnow()
                db.session.add(deployment)
                db.session.commit()
            else:
                logger.warning("%s: Wrong md5sum for mydata.tgz: %s" % (server.get("id"), md5sum))
            ssh.close()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            logger.exception("Could not connect to %s" % server.get("ip"))


def tc_reboot_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            successful_step = True
            if is_file_ssh(ssh, "/mnt/sdcard_boot/bootcode.bin") != 0:
                successful_step = False
                logger.warning("%s: bootcode.bin is still here!. Can not reboot." % server.get("id"))
            if successful_step:
                logger.info("Reboot the node '%s' to start on the tinyCore system" % server.get("id"))
                ssh.exec_command("reboot")
                deployment.tc_reboot_fct()
                deployment.updated_at = datetime.datetime.utcnow()
                db.session.add(deployment)
                db.session.commit()
            ssh.close()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            logger.warning("Could not connect to %s" % server.get("ip"))


def tc_fdisk_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        environment = [environment for environment in CLUSTER_CONFIG.get("environments")
                if environment.get("name") == deployment.environment][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username=environment.get("ssh_user"), timeout=1.0)
            (stdin, stdout, stderr) = ssh.exec_command("fdisk -l | grep mmcblk0 | wc -l")
            nb_partition = int(stdout.readlines()[0]) - 1
            logger.info("%s: %d detected partitions" % (server.get("id"), nb_partition))
            if nb_partition == 2:
                # Delete the second partition
                subprocess.run("ssh -o 'StrictHostKeyChecking no' tc@%s \"(echo d; echo 2; echo w; echo q) | sudo fdisk -u /dev/mmcblk0\"" % server.get("ip"), shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                # Create a partition with the whole free space
                subprocess.run("ssh -o 'StrictHostKeyChecking no' tc@%s \"(echo n; echo p; echo 2; echo '92160'; echo ''; echo w; echo q) | sudo fdisk -u /dev/mmcblk0; sudo reboot\"" % server.get("ip"), shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            deployment.tc_fdisk_fct()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
            ssh.close()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            logger.warning("Could not connect to %s" % server.get("ip"))


def tc_resize_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        environment = [environment for environment in CLUSTER_CONFIG.get("environments")
                if environment.get("name") == deployment.environment][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username=environment.get("ssh_user"), timeout=1.0)
            ssh.exec_command("sudo resize2fs /dev/mmcblk0p2")
            (stdin, stdout, stderr) = ssh.exec_command("df -h /dev/mmcblk0p2 | tail -n 1 | awk '{print $4}'")
            output = stdout.readlines()[0].strip()
            unit = output[-1:]
            partition_size = float(output[:-1])
            # Check if resize has been successful (partition's size should be larger than 4 GB)
            if unit == 'G':
                deployment.tc_resize_fct()
                deployment.updated_at = datetime.datetime.utcnow()
                db.session.add(deployment)
                db.session.commit()
            else:
                logger.warning("Wrong partition size for %s: %s" % (server.get("id"), output))
            ssh.close()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            logger.warning("Could not connect to %s" % server.get("ip"))


def tc_ssh_user_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        environment = [environment for environment in CLUSTER_CONFIG.get("environments")
                if environment.get("name") == deployment.environment][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username=environment.get("ssh_user"), timeout=1.0)
            if len(deployment.public_key) > 0:
                # Add the public key of the user
                cmd = "echo '\n%s' >> /home/tc/.ssh/authorized_keys && filetool.sh -b && sudo reboot" % deployment.public_key
                ssh.exec_command(cmd)
            if deployment.c9pwd is not None and len(deployment.c9pwd) > 0:
                # Change the tc password
                cmd = "echo -e '%s\n%s' | sudo passwd tc" % (deployment.c9pwd, deployment.c9pwd)
                ssh.exec_command(cmd)
            deployment.tc_ssh_user_fct()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
            ssh.close()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            logger.warning("Could not connect to %s" % server.get("ip"))


# Hard Reboot nodes (off -> on -> check SSH)
def off_requested_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        # Turn off port
        turn_off_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
        deployment.off_requested_fct()
        db.session.add(deployment)
        db.session.commit()


def on_requested_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        # Turn off port
        turn_on_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
        deployment.on_requested_fct()
        db.session.add(deployment)
        db.session.commit()


def reboot_check_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        environment = [environment for environment in CLUSTER_CONFIG.get("environments")
                if environment.get("name") == deployment.environment][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username=environment.get("ssh_user"), timeout=1.0)
            # Update the deployment
            deployment.reboot_check_fct()
            db.session.add(deployment)
            db.session.commit()
            ssh.close()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            updated = datetime.datetime.strptime(str(deployment.updated_at), '%Y-%m-%d %H:%M:%S')
            elapsedTime = (datetime.datetime.utcnow() - updated).total_seconds()
            logger.info("Could not connect to %s since %d seconds" % (server.get("ip"), elapsedTime))


# Destroying deployments
def destroy_request_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        # Turn off port
        turn_off_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
        deployment.destroy_request_fct()
        db.session.add(deployment)
        db.session.commit()


def destroying_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        can_connect = True
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            ssh.close()
        except (BadHostKeyException, AuthenticationException,
                SSHException, socket.error) as e:
            can_connect = False
        if not can_connect:
            deployment.destroying_fct()
            db.session.add(deployment)
            db.session.commit()
