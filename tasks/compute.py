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


def nfs_boot_conf_fct(deployments):
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


def nfs_boot_off_fct(deployments):
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


def nfs_boot_on_fct(deployments):
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


def env_copy_fct(deployments):
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
            ssh.exec_command(screen_deploy_cmd)
            # Update the deployment
            deployment.env_copy_fct()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            print(e)
            print("Could not connect to %s" % server.get("ip"))


def env_check_fct(deployments):
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
                deployment.env_check_fct()
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


def fs_mount_fct(deployments):
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
            # Mount the boot partition of the SD CARD
            cmd = "mount /dev/mmcblk0p1 /mnt/sdcard_boot"
            ssh.exec_command(cmd)
            # Mount the root partition of the SD CARD
            cmd = "mount /dev/mmcblk0p2 /mnt/sdcard_fs"
            ssh.exec_command(cmd)
            # Update the deployment
            deployment.fs_mount_fct()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
        except (BadHostKeyException, AuthenticationException, SHException, socket.error) as e:
            print(e)
            print("Could not connect to %s" % server.get("ip"))


def fs_conf_fct(deployments):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            # Short circuit the bootcode.bin file on the SD CARD
            ssh.exec_command("mv /mnt/sdcard_boot/bootcode.bin /mnt/sdcard_boot/_bootcode.bin")
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
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            print(e)
            print("Could not connect to %s" % server.get("ip"))


def fs_check_fct(deployments):
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
            # Update the deployment
            if successful_step:
                deployment.fs_check_fct()
                deployment.updated_at = datetime.datetime.utcnow()
                db.session.add(deployment)
                db.session.commit()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            print(e)
            print("Could not connect to %s" % server.get("ip"))


def resize_off_fct(deployments):
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


def resize_on_fct(deployments):
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


def resize_inprogress_fct(deployments):
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
            print("Waiting %s: %d/40s" % (server.get("ip"), elapsedTime))


def resize_done_fct(deployments):
    for deployment in deployments:
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        # Turn on port
        turn_on_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
        deployment.resize_done_fct()
        deployment.updated_at = datetime.datetime.utcnow()
        db.session.add(deployment)
        db.session.commit()


def resize_check_fct(deployments):
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
            # Update the deployment
            if successful_step:
                deployment.resize_check_fct()
            else:
                deployment.retry_resize()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            print(e)
            print("Could not connect to %s" % server.get("ip"))


def ssh_key_mount_fct(deployments):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            print("Could connect to %s" % server.get("ip"))
            # Mount the file system of the SD CARD
            cmd = "mount /dev/mmcblk0p2 /mnt/sdcard_fs"
            ssh.exec_command(cmd)
            deployment.ssh_key_mount_fct()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            print(e)
            print("Could not connect to %s" % server.get("ip"))

def ssh_key_copy_fct(deployments):
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
            cmd = "cp /root/.ssh/authorized_keys /mnt/sdcard_fs/root/.ssh/authorized_keys && sync"
            ssh.exec_command(cmd)
            deployment.ssh_key_copy_fct()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            print(e)
            print("Could not connect to %s" % server.get("ip"))


def ssh_key_user_fct(deployments):
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
            print(e)
            print("Could not connect to %s" % server.get("ip"))


def fs_boot_conf_fct(deployments):
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
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            print(e)
            print("Could not connect to %s" % server.get("ip"))


def fs_boot_off_fct(deployments):
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

def fs_boot_on_fct(deployments):
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


def fs_boot_check_fct(deployments):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            updated = datetime.datetime.strptime(str(deployment.updated_at), '%Y-%m-%d %H:%M:%S')
            elapsedTime = (datetime.datetime.utcnow() - updated).total_seconds()
            print("Could connect to %s after %s seconds" % (server.get("ip"), elapsedTime))
            # Update the deployment
            deployment.fs_boot_check_fct()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            updated = datetime.datetime.strptime(str(deployment.updated_at), '%Y-%m-%d %H:%M:%S')
            elapsedTime = (datetime.datetime.utcnow() - updated).total_seconds()
            print("Could not connect to %s since %d seconds" % (server.get("ip"), elapsedTime))
            if elapsedTime > 90:
                print("Retry the SSH configuration")
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


def ssh_config_2_fct(deployments):
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


def last_check_fct(deployments):
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
            deployment.last_check_fct()
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


def destroy_request_fct(deployments):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        # Turn off port
        turn_off_port(CLUSTER_CONFIG.get("switch").get("address"), server.get("port_number"))
        deployment.destroy_request_fct()
        db.session.add(deployment)
        db.session.commit()


def destroying_fct(deployments):
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
            deployment.destroying_fct()
            db.session.add(deployment)
            db.session.commit()
