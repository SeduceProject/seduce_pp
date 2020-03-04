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
            deploy_cmd = f"""rsh -o "StrictHostKeyChecking no" %s@%s "cat {environment_img_path}" | \
                    pv -n -p -s %s 2> /tmp/progress_{server['id']}.txt | dd of=/dev/mmcblk0 bs=4M conv=fsync""" % (
                            CLUSTER_CONFIG.get("controller").get("user"), CLUSTER_CONFIG.get("controller").get("ip"),
                            environment.get("img_size"))
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
            if ps_ssh(ssh, 'mmcblk0') == 0:
                # Update the deployment
                deployment.env_check_fct()
                deployment.updated_at = datetime.datetime.utcnow()
                db.session.add(deployment)
                db.session.commit()
            else:
                cmd = f"tail -n 1 /tmp/progress_{server['id']}.txt"
                ssh.exec_command(cmd)
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
                percent = stdout.readlines()[0].strip()
                deployment.label = percent
                db.session.add(deployment)
                db.session.commit()
            ssh.close()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            logger.warning("Could not connect to %s" % server.get("ip"))


def delete_partition_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            # Delete the second partition
            cmd = "(echo d; echo 2; echo w; echo q) | fdisk -u /dev/mmcblk0"
            (stdin, stdout, stderr) = ssh.exec_command(cmd)
            return_code = stdout.channel.recv_exit_status()
            # Update the deployment
            deployment.delete_partition_fct()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
            ssh.close()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            logger.warning("Could not connect to %s" % server.get("ip"))


def create_partition_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        environment = [environment for environment in CLUSTER_CONFIG.get("environments")
                if environment.get("name") == deployment.environment][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            # Create a partition with the whole free space
            cmd = ("(echo n; echo p; echo 2; echo '%s'; echo ''; echo w; echo q) | fdisk -u /dev/mmcblk0" %
                    environment.get("sector_start"))
            (stdin, stdout, stderr) = ssh.exec_command(cmd)
            return_code = stdout.channel.recv_exit_status()
            cmd = "partprobe"
            (stdin, stdout, stderr) = ssh.exec_command(cmd)
            return_code = stdout.channel.recv_exit_status()
            # Update the deployment
            deployment.create_partition_fct()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
            ssh.close()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            logger.warning("Could not connect to %s" % server.get("ip"))


def mount_partition_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            # Update the deployment
            cmd = "mount /dev/mmcblk0p1 boot_dir"
            (stdin, stdout, stderr) = ssh.exec_command(cmd)
            return_code = stdout.channel.recv_exit_status()
            cmd = "mount /dev/mmcblk0p2 fs_dir"
            (stdin, stdout, stderr) = ssh.exec_command(cmd)
            return_code = stdout.channel.recv_exit_status()
            deployment.mount_partition_fct()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
            ssh.close()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            logger.warning("Could not connect to %s" % server.get("ip"))


def resize_partition_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            cmd = "resize2fs /dev/mmcblk0p2"
            ssh.exec_command(cmd)
            # Update the deployment
            deployment.resize_partition_fct()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
            ssh.close()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            logger.warning("Could not connect to %s" % server.get("ip"))


def wait_resizing_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            if ps_ssh(ssh, 'resize2fs') == 0:
                # Update the deployment
                deployment.wait_resizing_fct()
                deployment.updated_at = datetime.datetime.utcnow()
                db.session.add(deployment)
                db.session.commit()
            ssh.close()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            logger.warning("Could not connect to %s" % server.get("ip"))


def system_conf_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            # Delete the bootcode.bin to force PXE boot
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
            cmd = "rm boot_dir/bootcode.bin"
            (stdin, stdout, stderr) = ssh.exec_command(cmd)
            return_code = stdout.channel.recv_exit_status()
            if deployment.environment == 'tiny_core':
                # Copy the custom tiny core with SSH keys
                cmd = "cp /environments/mydata.tgz fs_dir/tce/"
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
            if deployment.environment.startswith('raspbian_'):
                # Create the ssh file in the boot partition to start SSH on startup
                cmd = "touch boot_dir/ssh"
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
                # Avoid the execution of the expand/resize script
                cmd = "sed -i 's:init=.*$::' boot_dir/cmdline.txt"
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
                # Create a ssh folder in the root folder of the SD CARD's file system
                cmd = "mkdir fs_dir/root/.ssh"
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
                # Add the public key of the server
                cmd = "cp /root/.ssh/authorized_keys fs_dir/root/.ssh/authorized_keys"
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
            if deployment.environment == 'raspbian_cloud9':
                cmd = "echo '#!/bin/sh\nnodejs /var/lib/c9sdk/server.js -l 0.0.0.0 --listen 0.0.0.0 --port 8181 \
                        -a admin:%s -w /workspace' > fs_dir/usr/local/bin/c9" % deployment.c9pwd
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
            if deployment.environment == 'raspbian_buster':
                cmd = "chroot fs_dir/ update-rc.d ssh enable"
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
            # Copy boot files to the tftp folder
            tftpboot_node_folder = "/tftpboot/%s" % server.get("id")
            # Do NOT copy the *.dat files of the boot partition, they immensely slow down the raspberry
            cmd = f"scp -o 'StrictHostKeyChecking no' -r root@{server.get('ip')}:\"boot_dir/*.gz boot_dir/*.dtb \
                    boot_dir/*.img boot_dir/*.txt boot_dir/overlays/\" {tftpboot_node_folder}/"
            subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Reboot to initialize the operating system
            (stdin, stdout, stderr) = ssh.exec_command("reboot")
            # Update the deployment
            deployment.system_conf_fct()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
            ssh.close()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            logger.warning("Could not connect to %s" % server.get("ip"))


def user_conf_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        environment = [environment for environment in CLUSTER_CONFIG.get("environments")
                if environment.get("name") == deployment.environment][0]
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username=environment.get("ssh_user"), timeout=1.0)
            if deployment.environment == 'tiny_core':
                if len(deployment.public_key) > 0:
                    # Add the public key of the user
                    cmd = "echo '\n%s' >> /home/tc/.ssh/authorized_keys" % deployment.public_key
                    (stdin, stdout, stderr) = ssh.exec_command(cmd)
                    return_code = stdout.channel.recv_exit_status()
                # Change the 'tc' user password
                cmd = "echo -e '%s\n%s' | sudo passwd tc; filetool.sh -b" % (deployment.c9pwd, deployment.c9pwd)
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
            if deployment.environment.startswith('raspbian_'):
                if len(deployment.public_key) > 0:
                    cmd = "echo '\n%s' >> .ssh/authorized_keys" % deployment.public_key
                    (stdin, stdout, stderr) = ssh.exec_command(cmd)
                    return_code = stdout.channel.recv_exit_status()
                # Change the 'pi' user password
                cmd = "echo -e '%s\n%s' | sudo passwd pi" % (deployment.c9pwd, deployment.c9pwd)
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
            # Update the deployment
            deployment.user_conf_fct()
            deployment.updated_at = datetime.datetime.utcnow()
            db.session.add(deployment)
            db.session.commit()
            ssh.close()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            updated = datetime.datetime.strptime(str(deployment.updated_at), '%Y-%m-%d %H:%M:%S')
            elapsedTime = (datetime.datetime.utcnow() - updated).total_seconds()
            logger.warning("Could not connect to %s since %d seconds" % (server.get("ip"), elapsedTime))


def last_check_fct(deployments, logger):
    for deployment in deployments:
        # Get description of the server that will be deployed
        server = [server for server in CLUSTER_CONFIG.get("nodes") if server.get("id") == deployment.server_id][0]
        environment = [environment for environment in CLUSTER_CONFIG.get("environments")
                if environment.get("name") == deployment.environment][0]
        # By default the deployment should be concluded
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username=environment.get("ssh_user"), timeout=1.0)
            finish_init = True
            # Implement a mecanism that execute the init script
            if deployment.init_script is not None and len(deployment.init_script) > 0:
                ftp = ssh.open_sftp()
                finish_init = False
                if "started_init_script" not in ftp.listdir("/tmp/"):
                    # Generate random title
                    random_file_name = str(uuid.uuid1())
                    random_file_path = f"/tmp/{random_file_name}"
                    with open(random_file_path, mode="w") as f:
                        if deployment.environment.startswith('raspbian_'):
                            f.write("DEBIAN_FRONTEND=noninteractive\n")
                        f.write(deployment.init_script)
                    ftp.put(random_file_path, "/tmp/init_script.sh")
                    if "init_script.sh" not in ftp.listdir("/tmp"):
                        logger.error(f"\"init_script.sh\" not in /tmp")
                        continue
                    # Launch init script
                    cmd = "touch /tmp/started_init_script; sed -i 's/\r$//' /tmp/init_script.sh; \
                            %s /tmp/init_script.sh; touch /tmp/finished_init_script" % environment.get("shell")
                    ssh.exec_command(cmd)
                if "finished_init_script" in ftp.listdir("/tmp/"):
                    finish_init = True
                ftp.close()
            ssh.close()
            logger.info("%s: finish_init_script: %s" % (server.get('id'), finish_init))
            finish_deployment = environment.get("ready")(server, environment)
            logger.info("%s: finish_deployment: %s" % (server.get('id'), finish_deployment))
            if finish_init and finish_deployment:
                deployment.last_check_fct()
                deployment.updated_at = datetime.datetime.utcnow()
                db.session.add(deployment)
                db.session.commit()
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
