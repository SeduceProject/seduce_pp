from database.connector import open_session, close_session
from database.states import select_process, use_env_ssh_user
from database.tables import Deployment, User
from glob import glob
from lib.config_loader import get_cluster_desc, load_cluster_desc
from lib.dgs121028p import turn_on_port, turn_off_port
from paramiko.ssh_exception import BadHostKeyException, AuthenticationException, SSHException
import datetime, json, logging, os, paramiko, re, requests, shutil, socket, subprocess, sys, time, uuid

def exec_node_fct(fct_name, node):
    try:
        logger = logging.getLogger("STATE_EXEC")
        state_fct = getattr(sys.modules[__name__], fct_name)
        return state_fct(node, get_cluster_desc(), logger)
    except:
        logger.exception("[%s] node state function error" % node.node_name)
    return False


# Deploy environments
def boot_conf_exec(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    # Create a folder containing network boot files that will be served via TFTP
    tftpboot_template_folder = "/tftpboot/rpiboot_uboot"
    tftpboot_node_folder = "/tftpboot/%s" % server["id"]
    if os.path.isdir(tftpboot_node_folder):
        shutil.rmtree(tftpboot_node_folder)
    os.mkdir(tftpboot_node_folder)
    for tftpfile in glob("%s/*" % tftpboot_template_folder):
        os.symlink(tftpfile, tftpfile.replace(tftpboot_template_folder, tftpboot_node_folder))
    return True


def turn_off_exec(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    # Turn off port
    turn_off_port(server["switch"], server["port_number"])
    return True


def turn_on_exec(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    # Turn on port
    turn_on_port(server["switch"], server["port_number"])
    return True


def turn_on_post(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    ret = os.system("ping -W 1 -c 1 %s" % server["ip"])
    return ret == 0


def ssh_nfs_post(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server["ip"], username="root", timeout=1.0)
        # Check the booted system is the NFS system
        (stdin, stdout, stderr) = ssh.exec_command("cat /etc/hostname")
        return_code = stdout.channel.recv_exit_status()
        myname = stdout.readlines()[0].strip()
        ssh.close()
        if myname == "nfspi":
            return True
        else:
            logger.error("[%s] fail to detect the NFS filesystem: wrong hostname '%s'" % (server["name"], myname))
            return False
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("[%s] SSH connection failed" % server["name"])
    return False


def env_copy_exec(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    environment = cluster_desc["environments"][node.environment]
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server["ip"], username="root", timeout=1.0)
        # Get the path to the IMG file
        img_path = cluster_desc["img_dir"] + environment["img_name"]
        logger.info("[%s] copy %s to the SDCARD" % (server["name"], img_path))
        # Write the image of the environment on SD card
        deploy_cmd = "rsh -o StrictHostKeyChecking=no %s@%s 'cat %s' | tar xzOf - | \
                pv -n -p -s %s 2> progress-%s.txt | dd of=/dev/mmcblk0 bs=4M conv=fsync &" % (
                cluster_desc["pimaster"]["user"], cluster_desc["pimaster"]["ip"], img_path,
                environment["img_size"], server["name"])
        (stdin, stdout, stderr) = ssh.exec_command(deploy_cmd)
        return_code = stdout.channel.recv_exit_status()
        ssh.close()
        node.temp_info = 0
        if return_code == 0:
            return True
        else:
            logger.error("[%s] wrong return code while copying the OS: %d" % (server["name"], return_code))
            return False
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("[%s] SSH connection failed" % server["name"])
    return False


def env_copy_post(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server["ip"], username="root", timeout=1.0)
        if ps_ssh(ssh, "mmcblk0") > 0:
            ret_fct = True
        else:
            ret_fct = False
        ssh.close()
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("[%s] SSH connection failed" % server["name"])
    return ret_fct


def env_check_exec(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    environment = cluster_desc["environments"][node.environment]
    ret_fct = False
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server["ip"], username="root", timeout=1.0)
        if ps_ssh(ssh, "mmcblk0") == 0:
            ret_fct = True
        else:
            cmd = f"tail -n 1 progress-{server['name']}.txt"
            (stdin, stdout, stderr) = ssh.exec_command(cmd)
            return_code = stdout.channel.recv_exit_status()
            output = stdout.readlines()
            if len(output) == 0:
                logger.warning("%s: no progress value for the running environment copy" % server["ip"])
                updated = datetime.datetime.strptime(str(node.updated_at), "%Y-%m-%d %H:%M:%S")
                elapsedTime = (datetime.datetime.now() - updated).total_seconds()
                # Compute the progress value with an assumed transfert rate of 8 MB/s
                percent = elapsedTime * 8000000 * 100 / environment["img_size"]
            else:
                percent = output[0].strip()
            node.temp_info = percent
        ssh.close()
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("[%s] SSH connection failed" % server["name"])
    return ret_fct


def delete_partition_exec(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server["ip"], username="root", timeout=1.0)
        # Register the size of the existing partition
        cmd = "rm progress-%s.txt; fdisk -l /dev/mmcblk0" % server["name"]
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        output = stdout.readlines()
        # Partition size in sectors
        node.temp_info = int(output[-1].split()[3])
        # Delete the second partition
        cmd = "(echo d; echo 2; echo w) | fdisk -u /dev/mmcblk0"
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        ssh.close()
        return True
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("[%s] SSH connection failed" % server["name"])
    return False


def create_partition_exec(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    environment = cluster_desc["environments"][node.environment]
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server["ip"], username="root", timeout=1.0)
        moreMB = int(node.system_size)
        if moreMB == 8:
            logger.info("[%s] create a partition with the whole free space" % server["name"])
            cmd = ("(echo n; echo p; echo 2; echo '%s'; echo ''; echo w) | fdisk -u /dev/mmcblk0" %
                    environment["sector_start"])
        else:
            # Total size of the new partition in sectors (512B)
            moreSpace = int(node.temp_info) + (moreMB * 1024 * 1024 / 512)
            logger.info("[%s] create a partition with a size of %d sectors" % (server["name"], moreSpace))
            cmd = ("(echo n; echo p; echo 2; echo '%s'; echo '+%d'; echo w) | fdisk -u /dev/mmcblk0" %
                    (environment["sector_start"], moreSpace))
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        cmd = "partprobe"
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        ssh.close()
        return True
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("[%s] SSH connection failed" % server["name"])
    return False


def mount_partition_exec(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server["ip"], username="root", timeout=1.0)
        # Update the deployment
        cmd = "mount /dev/mmcblk0p1 boot_dir"
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        cmd = "mount /dev/mmcblk0p2 fs_dir"
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        ssh.close()
        return True
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("[%s] SSH connection failed" % server["name"])
    return False


def mount_partition_post(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server["ip"], username="root", timeout=1.0)
        # Check the boot_dir mount point
        cmd = "ls boot_dir/ | wc -l"
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        output = stdout.readlines()
        nb_files = int(output[-1].strip())
        if nb_files < 5:
            logger.error("[%s] boot partition is not mounted" % server["name"])
            return False
        # Delete the bootcode.bin file to prevent RPI3 to boot from SDCARD
        cmd = "rm boot_dir/bootcode.bin"
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        # Check the fs_dir mount point
        cmd = "ls fs_dir/ | wc -l"
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        output = stdout.readlines()
        nb_files = int(output[-1].strip())
        if nb_files < 2:
            logger.error("[%s] fs partition is not mounted" % server["name"])
            return False
        return True
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("[%s] SSH connection failed" % server["name"])
    return False


def resize_partition_exec(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server["ip"], username="root", timeout=1.0)
        cmd = "resize2fs /dev/mmcblk0p2 &> /dev/null &"
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        ssh.close()
        return True
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("[%s] SSH connection failed" % server["name"])
    return False


def resize_partition_post(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    try:
        ret_fct = False
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server["ip"], username="root", timeout=1.0)
        if ps_ssh(ssh, "resize2fs") > 0:
            ret_fct = True
        else:
            # Parse the output of the resizefs command
            cmd = "resize2fs /dev/mmcblk0p2"
            (stdin, stdout, stderr) = ssh.exec_command(cmd)
            return_code = stdout.channel.recv_exit_status()
            output = stderr.readlines()
            if len(output) > 2:
                if 'Nothing to do!' in output[1]:
                    ret_fct = True
        ssh.close()
        return ret_fct
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("[%s] SSH connection failed" % server["name"])
    return False


def wait_resizing_exec(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server["ip"], username="root", timeout=1.0)
        ret_fct = False
        if ps_ssh(ssh, "resize2fs") == 0:
            ret_fct = True
        ssh.close()
        return ret_fct
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("[%s] SSH connection failed" % server["name"])
    return False


def system_conf_exec(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    environment = cluster_desc["environments"][node.environment]
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server["ip"], username="root",
            timeout=1.0,
            banner_timeout=1.0,
            auth_timeout=1.0)
        if environment["type"] == "default":
            if environment["name"].startswith("ubuntu"):
                # Set the password of the 'ubuntu' user
                cmd = "sed -i 's/tototiti/%s/' boot_dir/user-data" % node.system_pwd
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
                # Set the hostname to modify the bash prompt
                cmd = "echo '%s' > fs_dir/etc/hostname" % server["name"]
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
            if environment["name"].startswith("raspbian"):
                # Create the ssh file in the boot partition to start SSH on startup
                cmd = "touch boot_dir/ssh"
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
                # Avoid the execution of the expand/resize script
                cmd = "sed -i 's:init=.*$::' boot_dir/cmdline.txt"
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
                # Set the hostname to modify the bash prompt
                cmd = "echo '%s' > fs_dir/etc/hostname" % server["name"]
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
            if environment["name"] == "raspbian_cloud9":
                cmd = "sed -i 's/-a :/-a admin:%s/' fs_dir/etc/systemd/system/cloud9.service" % node.system_pwd
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
            if environment["name"] == "raspbian_ttyd":
                cmd = "sed -i 's/toto/%s/' fs_dir/etc/rc.local" % node.system_pwd
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
        else:
            if environment["name"].startswith("raspbian"):
                # Set the hostname to modify the bash prompt
                cmd = "echo '%s' > fs_dir/etc/hostname" % server["name"]
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
        # Copy boot files to the tftp folder
        tftpboot_node_folder = "/tftpboot/%s" % server["id"]
        # Delete the existing tftp directory
        shutil.rmtree(tftpboot_node_folder)
        os.mkdir(tftpboot_node_folder)
        cmd = "scp -o 'StrictHostKeyChecking no' -r root@%s:boot_dir/* %s" % (server["ip"], tftpboot_node_folder)
        subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Reboot to initialize the operating system
        (stdin, stdout, stderr) = ssh.exec_command("reboot")
        return_code = stdout.channel.recv_exit_status()
        ret_val = True
        if return_code != 0:
            logger.error("[%s] soft reboot failure, hard rebooting" % server["name"]);
            # Set the state after the reboot
            node.temp_info = "ssh_system"
            # Turn off/on the node
            node.process = "reboot"
            node.state = select_process("reboot", node.environment)[0]
            # Do not load the next state
            ret_val = False
        ssh.close()
        # Check that the node is turned off
        if ret_val:
            ret = 0
            while ret == 0:
                logger.info("[%s] Waiting lost connection..." % server["name"])
                time.sleep(1)
                ret = os.system("ping -W 1 -c 1 %s" % server["ip"])
            return ret != 0
        return ret_val
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.exception("Debuging")
        logger.warning("[%s] SSH connection failed" % server["name"])
    return False


def ssh_system_post(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    environment = cluster_desc["environments"][node.environment]
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server["ip"], username=environment["ssh_user"], timeout=1.0)
        # Check the booted system is the NFS system
        (stdin, stdout, stderr) = ssh.exec_command("cat /etc/hostname")
        return_code = stdout.channel.recv_exit_status()
        myname = stdout.readlines()[0].strip()
        ssh.close()
        if myname == "nfspi":
            logger.error("[%s] fail to detect the OS filesystem: wrong hostname '%s'" % (server["name"], myname))
            return False
        else:
            return True
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("[%s] SSH connection failed" % server["name"])
    return False


def user_conf_exec(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    environment = cluster_desc["environments"][node.environment]
    ret_val = True
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server["ip"], username=environment["ssh_user"],
            timeout=1.0,
            banner_timeout=1.0,
            auth_timeout=1.0)
        (stdin, stdout, stderr) = ssh.exec_command("cat /etc/hostname")
        return_code = stdout.channel.recv_exit_status()
        myname = stdout.readlines()[0].strip()
        if myname == "nfspi":
            logger.error("[%s] hangs on the NFS filesystem" % server["name"])
            ret_val = False
        else:
            # Get the user SSH key from the DB
            db_session = open_session()
            db_user = db_session.query(User).filter_by(id = node.user_id).first()
            my_ssh_keys = ""
            if db_user.ssh_key is not None and len(db_user.ssh_key) > 0:
                my_ssh_keys = "\n%s" % db_user.ssh_key
            if node.public_key is not None and len(node.public_key) > 0:
                my_ssh_keys = "%s\n%s" % (my_ssh_keys, node.public_key)
            if len(my_ssh_keys) > 0:
                # Add the public key of the user
                cmd = "echo '%s' >> .ssh/authorized_keys" % my_ssh_keys
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
            if node.environment == "tiny_core":
                # Change the 'tc' user password
                cmd = "echo -e '%s\n%s' | sudo passwd tc; filetool.sh -b" % (
                        node.system_pwd, node.system_pwd)
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
            if node.environment.startswith("raspbian"):
                # Change the 'pi' user password
                cmd = "echo -e '%s\n%s' | passwd pi" % (node.system_pwd, node.system_pwd)
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
            close_session(db_session)
        ssh.close()
        return ret_val
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("[%s] SSH connection failed" % server["name"])
    return False


def user_script_exec(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    environment = cluster_desc["environments"][node.environment]
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server["ip"], username=environment["ssh_user"],
            timeout=1.0,
            banner_timeout=1.0,
            auth_timeout=1.0)
        finish_init = True
        # Implement a mecanism that execute the init script
        if node.init_script is not None and len(node.init_script) > 0:
            ftp = ssh.open_sftp()
            finish_init = False
            if "started_init_script" not in ftp.listdir("/tmp/"):
                # Generate random title
                random_file_name = str(uuid.uuid1())
                random_file_path = f"/tmp/{random_file_name}"
                with open(random_file_path, mode="w") as f:
                    if node.environment.startswith("raspbian"):
                        f.write("DEBIAN_FRONTEND=noninteractive\n")
                    f.write(node.init_script)
                ftp.put(random_file_path, "/tmp/init_script.sh")
                if "init_script.sh" in ftp.listdir("/tmp"):
                    # Launch init script
                    cmd = "touch /tmp/started_init_script; sed -i 's/\r$//' /tmp/init_script.sh; \
                            %s /tmp/init_script.sh; touch /tmp/finished_init_script" % environment["shell"]
                    ssh.exec_command(cmd)
                else:
                    logger.error("[%s] 'init_script.sh' not in /tmp" % server["name"])
            if "finished_init_script" in ftp.listdir("/tmp/"):
                finish_init = True
            ftp.close()
        ssh.close()
        logger.info("[%s] finish_init_script: %s" % (server["name"], finish_init))
        no_check = True
        finish_deployment = False
        if environment["name"] == "raspbian_cloud9":
            no_check = False
            finish_deployment = check_cloud9_is_ready(server, environment, logger)
        if no_check:
            finish_deployment = check_ssh_is_ready(server, environment, logger)
        logger.info("[%s] finish_deployment: %s" % (server["name"], finish_deployment))
        return finish_init and finish_deployment
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("[%s] SSH connection failed" % server["name"])
    return False


# Test if the processus exists on the remote node
def ps_ssh(ssh_session, process):
    try:
        (stdin, stdout, stderr) = ssh_session.exec_command("ps aux | grep %s | grep -v grep | wc -l" % process)
        return_code = stdout.channel.recv_exit_status()
        output = stdout.readlines()
        return int(output[0].strip())
    except SSHException:
        return -1


# Check deployed environments
def check_ssh_is_ready(node_desc, env_desc, logger):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(node_desc["ip"], username=env_desc["ssh_user"], timeout=1.0)
        ssh.close()
        return True
    except:
        logger.warning("[%s] SSH connection failed" % server["name"])
        return False


def check_cloud9_is_ready(node_desc, env_desc, logger):
    if not "public_ip" in node_desc:
        ret_bool = True
    else:
        ret_bool = False
        cloud9_ide_url = "http://%s/ide.html" % (node_desc["public_ip"])
        result = requests.get(cloud9_ide_url)
        if result.status_code == 200 and "<title>Cloud9</title>" in result.text:
            ret_bool = True
        if result.status_code == 401 and "Unauthorized" in result.text:
            ret_bool = True
        if not ret_bool:
            logger.error("[%s] status code %d" % (node_desc["name"], result.status_code))
    return ret_bool


# Create environment images
def img_part_exec(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    environment = cluster_desc["environments"][node.environment]
    logger.info("[%s] create the image '%s'" % (server["name"], node.temp_info))
    ret_fct = False
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server["ip"], username=environment["ssh_user"], timeout=1.0)
        cmd = "fdisk -l /dev/mmcblk0"
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        output = stdout.readlines()
        if len(output) > 10:
            logger.error("[%s] more than 2 partitions detected. Can not create another partition!" %
            server["name"])
            ret_fct = False
        else:
            # Check there is enough free space on the disk
            nb_sectors = int(output[0].split()[-2])
            last_sector = int(output[-1].split()[2])
            # Size of the new partition (size occupied by the filesystem * 1.7 to compress the image) in sectors
            partition_size = int(last_sector * 1.7)
            # We need partition_size available sectors + 20 sectors
            if nb_sectors - last_sector > partition_size + 20:
                # Install the pv tool
                cmd = "apt install pv"
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
                logger.info("[%s] nb sectors: %d, last sector: %d" % (server["name"], nb_sectors, last_sector))
                # Create a new partition that begins at (last_sector + 20 sectors)
                cmd = ("(echo n; echo ''; echo ''; echo '%d'; echo '+%d'; echo w) | fdisk -u /dev/mmcblk0" %
                        ((last_sector + 20), partition_size))
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
                # Save the end of the user partitions
                node.temp_info = "%s %d" % (node.temp_info, last_sector)
                ret_fct = True
            else:
                logger.error("[%s] no enough space on the disk. Only %d sectors available, %d required sectors" %
                        (server["name"], (nb_sectors - last_sector), partition_size))
        ssh.close()
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("[%s] SSH connection failed" % server["name"])
    return ret_fct


def img_format_exec(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    environment = cluster_desc["environments"][node.environment]
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server["ip"], username=environment["ssh_user"], timeout=1.0)
        cmd = "partprobe"
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        # Get the name of the new partition
        cmd = "ls /dev/mmcblk0p*"
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        output = stdout.readlines()
        partition_name = output[-1].strip()
        logger.info("[%s] format the partition '%s'" % (server["name"], partition_name))
        cmd = "mkfs.ext4 %s &> /dev/null &" % partition_name
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        ssh.close()
        # Save the partition name
        node.temp_info = "%s %s" % (node.temp_info, partition_name)
        return True
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("[%s] SSH connection failed" % server["name"])
    return False


def img_copy_exec(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    environment = cluster_desc["environments"][node.environment]
    ret_fct = False
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server["ip"], username=environment["ssh_user"], timeout=1.0)
        end_partition = int(node.temp_info.split()[1])
        partition_name = node.temp_info.split()[2]
        cmd = "mkdir img_part"
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        if ps_ssh(ssh, partition_name) == 0:
            # Check if the new partition is mounted
            cmd = "mount -f | grep img_part"
            (stdin, stdout, stderr) = ssh.exec_command(cmd)
            return_code = stdout.channel.recv_exit_status()
            output = stdout.readlines()
            mounted_part = len(output) > 0
            if not mounted_part:
                logger.info("[%s] mount the partition '%s'" % (server["name"], partition_name))
                cmd = "mount %s img_part" % partition_name
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
                mounted_part = return_code == 0
            if mounted_part:
                # Write the size of the uncompressed image file to the JSON
                env_name = node.temp_info.split()[0]
                env_file_path = cluster_desc["env_cfg_dir"] + env_name + ".json"
                with open(env_file_path, "r") as jsonfile:
                    env_data = json.load(jsonfile)
                env_data["img_size"] = (end_partition + 10) * 512
                with open(env_file_path, "w") as jsonfile:
                    json.dump(env_data, jsonfile)
                # Copy the system to the image file
                cmd = "dd if=/dev/mmcblk0 of=img_part/%s.img bs=512 count=%d &" % (env_name, end_partition + 10)
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
                ret_fct = True
                node.temp_info = 0
            else:
                logger.error("[%s] can not mount the partition '%s'" % (server["name"], partition_name))
        ssh.close()
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("[%s] SSH connection failed" % server["name"])
    return ret_fct

def img_copy_check_exec(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    environment = cluster_desc["environments"][node.environment]
    ret_fct = False
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server["ip"], username=environment["ssh_user"], timeout=1.0)
        if ps_ssh(ssh, "count") == 0:
            ret_fct = True
        else:
            cmd = f"tail -n 1 progress-{server['name']}.txt"
            (stdin, stdout, stderr) = ssh.exec_command(cmd)
            return_code = stdout.channel.recv_exit_status()
            output = stdout.readlines()
            if len(output) == 0:
                logger.warning("[%s] no progress value for the running image copy" % server["name"])
                updated = datetime.datetime.strptime(str(node.updated_at), "%Y-%m-%d %H:%M:%S")
                elapsedTime = (datetime.datetime.now() - updated).total_seconds()
                # Compute the progress value with an assumed transfert rate of 8 MB/s
                percent = elapsedTime * 8000000 * 100 / environment["img_size"]
            else:
                percent = output[0].strip()
            node.temp_info = int(percent)
        ssh.close()
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("[%s] SSH connection failed" % server["name"])
    return ret_fct


def img_customize_exec(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    environment = cluster_desc["environments"][node.environment]
    ret_fct = False
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server["ip"], username=environment["ssh_user"], timeout=1.0)
        # Get a free loop device
        cmd = "losetup -f"
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        loop_device = stdout.readlines()[0].strip()
        logger.info("[%s] delete the third partition by using '%s'" % (server["name"], loop_device))
        # Link the .img file to the loop device
        cmd = "cd img_part; losetup -P %s *.img" % loop_device
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        # Delete the third partition
        cmd = "(echo d; echo 3; echo w) | fdisk -u %s" % loop_device
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        # Release the loop device
        cmd = "losetup -d %s" % loop_device
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        ret_fct = True
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("[%s] SSH connection failed" % server["name"])
    return ret_fct


def img_compress_exec(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    environment = cluster_desc["environments"][node.environment]
    ret_fct = False
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server["ip"], username=environment["ssh_user"], timeout=1.0)
        # Compress the filesystem image
        cmd = "cd img_part; gzip -9 *.img &"
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        ssh.close()
        ret_fct = True
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("[%s] SSH connection failed" % server["name"])
    return ret_fct


def img_compress_check_exec(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    environment = cluster_desc["environments"][node.environment]
    ret_fct = False
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server["ip"], username=environment["ssh_user"], timeout=1.0)
        if ps_ssh(ssh, "gzip") == 0:
            # Get both the filename and the size of the compressed image file
            cmd = "rm -f progress-{server['name']}.txt; cd img_part; ls -l *.img.gz | tail -n 1"
            (stdin, stdout, stderr) = ssh.exec_command(cmd)
            return_code = stdout.channel.recv_exit_status()
            output = stdout.readlines()[0].split()
            node.temp_info = "%s %s" % (output[-1], output[4])
            ret_fct = True
        else:
            cmd = f"tail -n 1 progress-{server['name']}.txt"
            (stdin, stdout, stderr) = ssh.exec_command(cmd)
            return_code = stdout.channel.recv_exit_status()
            output = stdout.readlines()
            if len(output) == 0:
                logger.warning("[%s] no progress value for the running image compression" % server["name"])
                updated = datetime.datetime.strptime(str(node.updated_at), "%Y-%m-%d %H:%M:%S")
                elapsedTime = (datetime.datetime.now() - updated).total_seconds()
                # Compute the progress value from past experiments on Pi 3B+
                percent = elapsedTime * 1500000 * 100 / environment["img_size"]
            else:
                percent = output[0].strip()
            node.temp_info = percent
        ssh.close()
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("[%s] SSH connection failed" % server["name"])
    return ret_fct


def upload_exec(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    environment = cluster_desc["environments"][node.environment]
    img_name = node.temp_info.split()[0]
    img_size = node.temp_info.split()[1]
    logger.info("[%s] upload the file '%s'" % (server["name"], img_name))
    cmd = f"""rsh -o "StrictHostKeyChecking no" %s@%s "cat img_part/%s" | \
                pv -n -p -s %s 2> /tmp/progress-{server["name"]}.txt | dd of=%s%s bs=4M conv=fsync &""" % (
                        environment["ssh_user"], server["ip"], img_name, img_size,
                        cluster_desc["img_dir"], img_name)
    subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    node.temp_info = 0
    return True


def upload_check_exec(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    environment = cluster_desc["environments"][node.environment]
    cmd = "ps aux | grep %s | grep -v grep | wc -l" % server["ip"]
    process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    nb_line = process.stdout.decode("utf-8").strip()
    if int(nb_line) == 0:
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server["ip"], username=environment["ssh_user"], timeout=1.0)
            cmd = f"rm progress-{server['name']}.txt"
            (stdin, stdout, stderr) = ssh.exec_command(cmd)
            return_code = stdout.channel.recv_exit_status()
            ssh.close()
            # Load the new environement to the cluster description
            load_cluster_desc()
            return True
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            logger.warning("[%s] SSH connection failed" % server["name"])
    else:
        cmd = f"tail -n 1 /tmp/progress-{server['name']}.txt"
        process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        output = process.stdout.decode("utf-8").strip()
        if len(output) == 0:
            logger.warning("[%s] no progress value for the running environment copy" % server["name"])
            updated = datetime.datetime.strptime(str(node.updated_at), "%Y-%m-%d %H:%M:%S")
            elapsedTime = (datetime.datetime.now() - updated).total_seconds()
            # Compute the progress value with an assumed transfert rate of 8 MB/s
            percent = elapsedTime * 8000000 * 100 / environment["img_size"]
        else:
            percent = output
        node.temp_info = int(percent)
    return False


# Hard Reboot nodes (turn_off -> turn_on -> coming_back)
def coming_back_exec(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    environment = cluster_desc["environments"][node.environment]
    try:
        # Test the SSH connection
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        if use_env_ssh_user(node.temp_info):
            ssh.connect(server["ip"], username=environment["ssh_user"], timeout=1.0)
        else:
            ssh.connect(server["ip"], username="root", timeout=1.0)
        ssh.close()
        # Come back to the deployment process
        node.process = "deploy"
        node.state = node.temp_info
        node.temp_info = None
        # Always return False to avoid rewriting the node.state property
        return False
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("[%s] SSH connection failed" % server["name"])
    return False


# Destroying deployments
def destroying_exec(node, cluster_desc, logger):
    server = cluster_desc["nodes"][node.node_name]
    # When destroying initialized deployments, the environment is unset
    if node.environment is not None:
        environment = cluster_desc["environments"][node.environment]
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            # Try to connect to the deployed environment
            ssh.connect(server["ip"], username=environment["ssh_user"], timeout=1.0)
            (stdin, stdout, stderr) = ssh.exec_command("rm -f /boot/bootcode.bin")
            return_code = stdout.channel.recv_exit_status()
            ssh.close()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            logger.info("[%s] can not connect to the deployed environment" %
                    server["name"])
            try:
                # Try to connect to the nfs environment
                ssh.connect(server["ip"], username="root", timeout=1.0)
                cmd = "mount /dev/mmcblk0p1 boot_dir"
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
                (stdin, stdout, stderr) = ssh.exec_command("rm -f boot_dir/bootcode.bin")
                return_code = stdout.channel.recv_exit_status()
                ssh.close()
            except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
                logger.info("[%s] can not connect to the NFS environment" % server["name"])
    # Delete the tftpboot folder
    tftpboot_node_folder = "/tftpboot/%s" % server["id"]
    if os.path.isdir(tftpboot_node_folder):
        shutil.rmtree(tftpboot_node_folder)
    return True
