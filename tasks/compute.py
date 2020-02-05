import celery
from database import db
from database import Deployment
from lib.config.cluster_config import CLUSTER_CONFIG
from redlock import RedLock
import os, traceback, sys
import shutil
from lib.dgs121028p import turn_on_port, turn_off_port
import time
import paramiko
from paramiko.ssh_exception import BadHostKeyException, AuthenticationException, SSHException
import socket
from lib.deployment import get_nfs_boot_cmdline, get_sdcard_boot_cmdline, get_sdcard_resize_boot_cmdline
import re
import random
import uuid
from sqlalchemy import or_
import datetime

# Global variables
rebooting_nodes = []

def collect_nodes(process, node_state):
    try:
        pending_deployments = Deployment.query.filter_by(state=node_state).all()
        if len(pending_deployments) > 0:
            print("### Processing %d deployments in '%s' state:" % (len(pending_deployments), node_state))
            print([d.server_id for d in pending_deployments])
            with RedLock("lock/deployments/%s" % node_state):
                process(pending_deployments)
        db.session.remove()
    except Exception:
            print("Exception in '%s' state:" % node_state)
            traceback.print_exc(file=sys.stdout)


def prepare_nfs_boot(deployments):
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
        deployment.prepare_nfs_boot()
        deployment.updated_at = datetime.datetime.utcnow()
        db.session.add(deployment)
        db.session.commit()


def init_reboot_nfs(deployments):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        # Turn off port
        turn_off_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
        # Update the deployment
        deployment.init_reboot_nfs()
        deployment.updated_at = datetime.datetime.utcnow()
        db.session.add(deployment)
        db.session.commit()


def start_reboot_nfs(deployments):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        # Turn on port
        turn_on_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
        # Update the deployment
        deployment.start_reboot_nfs()
        deployment.updated_at = datetime.datetime.utcnow()
        db.session.add(deployment)
        db.session.commit()


def conclude_reboot_nfs(deployments):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            print("Could connect to %s" % server.get("ip"))
            # Update the deployment
            deployment.conclude_reboot_nfs()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            print(e)
            print("Could not connect to %s" % server.get("ip"))


def prepare_deployment(deployments):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
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
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            print(e)
            print("Could not connect to %s" % server.get("ip"))


def deploy_env(deployments):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        environment = [environment for environment in CLUSTER_CONFIG.get("environments") if environment.get("name") == deployment.environment][0]
        environment_img_path = environment.get("img_path")
        print(server)
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            print("Could connect to %s" % server.get("ip"))
            # Configure the screen tool
            ssh.exec_command("chmod -R 777 /run/screen;")
            # Write the image of the environment on SD card
            deploy_cmd = f"""rm -f /tmp/done_{server['id']}.txt /tmp/progress_{server['id']}.txt; rsh -o "StrictHostKeyChecking no" %s@%s "cat {environment_img_path}" | dd of=/dev/mmcblk0 bs=4M conv=fsync status=progress 2>&1 | tee /tmp/progress_{server['id']}.txt; touch /tmp/done_{server['id']}.txt;""" % (CLUSTER_CONFIG.get("controller").get("user"), CLUSTER_CONFIG.get("controller").get("ip"))
            screen_deploy_cmd = "screen -d -m bash -c '%s'" % deploy_cmd
            print("execute cmd: %s" % screen_deploy_cmd)
            ssh.exec_command(screen_deploy_cmd)
            # Update the deployment
            deployment.deploy_env()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            print(e)
            print("Could not connect to %s" % server.get("ip"))


def deploy_env_finished(deployments):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            print("Could connect to %s" % server.get("ip"))
            # Write the image of the environment on SD card
            ftp = ssh.open_sftp()
            print(f"Looking for done_{server['id']}.txt") 
            if f"done_{server['id']}.txt" in ftp.listdir("/tmp"):
                # Update the deployment
                deployment.deploy_env_finished()
                deployment.updated_at = datetime.datetime.utcnow()
            else:
                # Get the progress
                if f"progress_{server['id']}.txt" in ftp.listdir("/tmp"):
                    cmd = f"""cat /tmp/progress_{server['id']}.txt"""
                    (stdin, stdout, stderr) = ssh.exec_command(cmd)
                    lines = stdout.readlines()
                    sublines = [sl.strip() for l in lines for sl in l.split("\r")]
                    if len(sublines) > 1:
                        output = re.sub('[^ a-zA-Z0-9./,()]', '', sublines[-1])
                        deployment.label = output
                        print(f"{server.get('ip')} ({deployment.id}) => {output}")
                else:
                    print(f"{server.get('ip')} ({deployment.id}) : NO /tmp/progress_{server['id']}.txt file!!!")
            ssh.close()
            db.session.add(deployment)
            db.session.commit()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            print(e)
            print("Could not connect to %s" % server.get("ip"))


def mount_filesystem(deployments):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
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
            # Update the deployment
            deployment.mount_filesystem()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
        except (BadHostKeyException, AuthenticationException, SHException, socket.error) as e:
            print(e)
            print("Could not connect to %s" % server.get("ip"))


def configure_sdcard_resize_boot(deployments):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            # Short circuit the bootcode.bin file on the SD CARD
            ftp = ssh.open_sftp()
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
            # /!\ here we check that changes have been committed to the SD card
            # Mount the boot partition of the SD CARD
            cmd = "mount /dev/mmcblk0p1 /mnt/sdcard_boot"
            ssh.exec_command(cmd)
            # Update the deployment
            deployment.configure_sdcard_resize_boot()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            print(e)
            print("Could not connect to %s" % server.get("ip"))


def filesystem_check(deployments):
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
                deployment.filesystem_check()
                deployment.updated_at = datetime.datetime.utcnow()
                db.session.add(deployment)
                db.session.commit()
            #else:
            #    deployment.retry_configure_sdcard()
            #    db.session.add(deployment)
            #    db.session.commit()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            print(e)
            print("Could not connect to %s" % server.get("ip"))


def turn_off_after_resize(deployments):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        # Turn off port
        turn_off_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
        # Update the deployment state
        deployment.turn_off_after_resize()
        deployment.updated_at = datetime.datetime.utcnow()
        db.session.add(deployment)
        db.session.commit()


def turn_on_after_resize(deployments):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        # Turn on port
        turn_on_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
        # Update the deployment state
        deployment.turn_on_after_resize()
        deployment.updated_at = datetime.datetime.utcnow()
        db.session.add(deployment)
        db.session.commit()


def off_nfs_boot(deployments):
    for deployment in deployments:
        updated = datetime.datetime.strptime(str(deployment.updated_at), '%Y-%m-%d %H:%M:%S')
        elapsedTime = (datetime.datetime.utcnow() - updated).total_seconds()
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        if elapsedTime >= 60:
            # Modify the boot PXE configuration file to resize the FS
            tftpboot_node_folder = "/tftpboot/%s" % server.get("id")
            text_file = open("%s/cmdline.txt" % tftpboot_node_folder, "w")
            text_file.write(get_nfs_boot_cmdline() % {"controller_ip": CLUSTER_CONFIG.get("controller").get("ip")})
            text_file.close()
            # Turn off port
            turn_off_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
            deployment.off_nfs_boot()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
        else:
            print("Waiting %s: %d/40s" % (server.get("ip"), elapsedTime))


def on_nfs_boot(deployments):
    for deployment in deployments:
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        # Turn on port
        turn_on_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
        deployment.on_nfs_boot()
        deployment.updated_at = datetime.datetime.utcnow()
        db.session.add(deployment)
        db.session.commit()


def conclude_reboot_nfs_after_resize(deployments):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            print("Could connect to %s" % server.get("ip"))
            # Update the deployment
            deployment.conclude_reboot_nfs_after_resize()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            print(e)
            print("Could not connect to %s" % server.get("ip"))


def sdcard_mount(deployments):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            # Ensure 'sdcard_boot' exists
            ssh.exec_command("mkdir -p /mnt/sdcard_boot")
            # Unmount the boot file system
            cmd = "umount /mnt/sdcard_fs"
            ssh.exec_command(cmd)
            # Mount the boot partition of the SD CARD
            cmd = "mount /dev/mmcblk0p2 /mnt/sdcard_fs"
            ssh.exec_command(cmd)
            deployment.sdcard_mount()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            print(e)
            print("Could not connect to %s" % server.get("ip"))


def collect_partition_uuid(deployments):
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
            print("partition_size: %f" % partition_size)
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
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            print(e)
            print("Could not connect to %s" % server.get("ip"))


def mount_public_key(deployments):
    for deployment in deployments:
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
            deployment.mount_public_key()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            print(e)
            print("Could not connect to %s" % server.get("ip"))

def deploy_public_key(deployments):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            print("Could connect to %s" % server.get("ip"))
            # Create a ssh folder in the root folder of the SD CARD's file system
            cmd = "mkdir -p /mnt/sdcard_fs/root/.ssh"
            ssh.exec_command(cmd)
            # Add the public key of the server
            cmd = "cp /root/.ssh/authorized_keys /mnt/sdcard_fs/root/.ssh/authorized_keys"
            ssh.exec_command(cmd)
            deployment.deploy_public_key()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            print(e)
            print("Could not connect to %s" % server.get("ip"))


def check_authorized_keys(deployments):
    for deployment in deployments:
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            # Check the number of lines of the authorized_keys file to ensure the SSH key copy
            cmd = "cat /mnt/sdcard_fs/root/.ssh/authorized_keys | wc -l"
            stdin, stdout, stderr = ssh.exec_command(cmd)
            lines = stdout.read().splitlines()
            # Convert bytes to ASCII to int
            wc_lines = int.from_bytes(lines[0], byteorder='big') - 48
            if wc_lines > 1:
                # Add the public key of the server (second try)
                cmd = "echo '\n%s' >> /mnt/sdcard_fs/root/.ssh/authorized_keys" % CLUSTER_CONFIG.get("controller").get("public_key")
                ssh.exec_command(cmd)
                # Add the public key of the user
                cmd = "echo '\n%s' >> /mnt/sdcard_fs/root/.ssh/authorized_keys" % deployment.public_key
                ssh.exec_command(cmd)
                # Secure the cloud9 connection
                if deployment.environment == 'raspbian_cloud9':
                    cmd = "echo '#!/bin/sh\nnodejs /var/lib/c9sdk/server.js -l 0.0.0.0 --listen 0.0.0.0 --port 8181 -a admin:%s -w /workspace' > /mnt/sdcard_fs/usr/local/bin/c9" % deployment.c9pwd
                    ssh.exec_command(cmd)
                if deployment.environment == 'raspbian_buster':
                    cmd = "chroot /mnt/sdcard_fs/ update-rc.d ssh enable"
                    ssh.exec_command(cmd)
                # Unmount the file system
                cmd = "umount /mnt/sdcard_fs"
                ssh.exec_command(cmd)
                # Update the deployment
                deployment.check_authorized_keys()
                deployment.updated_at = datetime.datetime.utcnow()
                db.session.add(deployment)
                db.session.commit()
            else:
                print("%s: Bad copy of authorized_keys: nb. lines %s" % (server.get("ip"), wc_lines))
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            print(e)
            print("Could not connect to %s" % server.get("ip"))


def prepare_sdcard_boot(deployments):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            # Ensure 'sdcard_boot' exists
            ssh.exec_command("mkdir -p /mnt/sdcard_boot")
            # Unmount the boot partition of the SD CARD
            cmd = "umount /mnt/sdcard_boot"
            ssh.exec_command(cmd)
            # Mount the boot partition of the SD CARD
            cmd = "mount /dev/mmcblk0p1 /mnt/sdcard_boot"
            ssh.exec_command(cmd)
            # Update the deployment
            deployment.prepare_sdcard_boot()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            print(e)
            print("Could not connect to %s" % server.get("ip"))


def do_sdcard_boot(deployments):
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
                sync
            """
            os.system(cmd)
            # Modify the boot PXE configuration file to mount its file system via NFS
            text_file = open("%s/cmdline.txt" % tftpboot_node_folder, "w")
            text_file.write(get_sdcard_boot_cmdline() % {"partition_uuid": partition_uuid})
            text_file.close()
            # Unmount the boot partition of the SD CARD
            cmd = "umount /mnt/sdcard_boot"
            ssh.exec_command(cmd)
            # Update the deployment
            deployment.do_sdcard_boot()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            print(e)
            print("Could not connect to %s" % server.get("ip"))


def off_reboot_sdcard(deployments):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        # Turn off port
        turn_off_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
        # Update the deployment
        deployment.off_reboot_sdcard()
        deployment.updated_at = datetime.datetime.utcnow()
        db.session.add(deployment)
        db.session.commit()

def on_reboot_sdcard(deployments):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        # Turn on port
        turn_on_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
        # Update the deployment
        deployment.on_reboot_sdcard()
        deployment.updated_at = datetime.datetime.utcnow()
        db.session.add(deployment)
        db.session.commit()


def conclude_reboot_sdcard(deployments):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            print("Could connect to %s" % server.get("ip"))
            # Update the deployment
            deployment.conclude_reboot_sdcard()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            print(e)
            print("Could not connect to %s" % server.get("ip"))


def finish_deployment(deployments):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        environment = [environment for environment in CLUSTER_CONFIG.get("environments") if
                       environment.get("name") == deployment.environment][0]
        # By default the deployment should be concluded
        finish_init = True
        finish_deployment = True
        # Implement a mecanism that execute the init script
        if deployment.init_script is not None and deployment.init_script != "":
            finish_init = False
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(server.get("ip"), username="root", timeout=1.0)
                print("Could connect to %s" % server.get("ip"))

                ftp = ssh.open_sftp()
                print(ftp)
                if "started_init_script" not in ftp.listdir("/tmp/"):
                    # Generate random title
                    random_file_name = str(uuid.uuid1())
                    random_file_path = f"/tmp/{random_file_name}"
                    with open(random_file_path, mode="w") as f:
                        f.write("DEBIAN_FRONTEND=noninteractive\n")
                        f.write(deployment.init_script)
                    ftp.put(random_file_path, "/tmp/init_script.sh")
                    if "init_script.sh" not in ftp.listdir("/tmp"):
                        print(f"ERROR: \"init_script.sh\" not in /tmp")
                        continue
                    # Launch init script
                    cmd = "touch /tmp/started_init_script; sed -i 's/\r$//' /tmp/init_script.sh; bash /tmp/init_script.sh; touch /tmp/finished_init_script"
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
            finish_deployment = environment.get("ready")(server)
        print("finish_init %s" % finish_init)
        print("finish_deployment %s" % finish_deployment)
        if finish_deployment and finish_init:
            deployment.finish_deployment()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()


def off_requested_fct(deployments):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        # Turn off port
        turn_off_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
        deployment.off_requested_fct()
        db.session.add(deployment)
        db.session.commit()


def on_requested_fct(deployments):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        # Turn off port
        turn_on_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
        deployment.on_requested_fct()
        db.session.add(deployment)
        db.session.commit()


def reboot_check_fct(deployments):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            print("Could connect to %s" % server.get("ip"))
            # Update the deployment
            deployment.reboot_check_fct()
            db.session.add(deployment)
            db.session.commit()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            print(e)
            print("Could not connect to %s" % server.get("ip"))


def process_destruction(deployments):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        # Turn off port
        turn_off_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
        deployment.process_destruction()
        db.session.add(deployment)
        db.session.commit()


def conclude_destruction(deployments):
    for deployment in deployments:
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

""" Not currently used...
@celery.task()
def detect_stuck_deployments():
    print("Checking deployments with servers that failed to reboot")
    # Use lock in context
    with RedLock("lock/check/stuck_deployment"):
        rebooting_deployments = Deployment.query.filter(or_(Deployment.state == "nfs_rebooting",
                                                          Deployment.state == "nfs_rebooting_after_resize",
                                                          Deployment.state == "sdcard_rebooting")).all()
        print(len(rebooting_deployments))
        for deployment in rebooting_deployments:
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
                now = datetime.datetime.utcnow()
                elapsed_time_since_last_update = (now - deployment.updated_at).total_seconds()
                if elapsed_time_since_last_update > 90:
                    deployment.updated_at = now
                    # Turn off port
                    print("Turn off %s" % server.get("ip"))
                    turn_off_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
                    rebooting_nodes.append(server)

@celery.task()
def boot_stuck_deployments():
    # Use lock in context
    with RedLock("lock/check/stuck_deployment"):
        if len(rebooting_nodes) > 0:
            print("Power on stuck nodes (#nodes: %d)" % len(rebooting_nodes))
            for server in rebooting_nodes:
                # Turn on port
                turn_on_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
            while len(rebooting_nodes) > 0:
                rebooting_nodes.pop(0)
"""

