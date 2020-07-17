from database.connector import open_session, close_session
from database.states import progress_forward, use_env_ssh_user
from database.tables import Deployment, User
from lib.config_loader import get_cluster_desc, load_cluster_desc
from lib.dgs121028p import turn_on_port, turn_off_port
from paramiko.ssh_exception import BadHostKeyException, AuthenticationException, SSHException
import datetime, json, logging, os, paramiko, re, requests, shutil, socket, subprocess, sys, time, uuid

# After rebooting, nodes that are not reachable after 300 s are tagged 'lost'.
# The 'lost' tag is removed when the deployment is destroyed.
lost_timeout = 300
lost_nodes = []

def is_lost(deployment, logger):
    logger.error('\'%s\' is lost. Hard reboot the node or destroy the deployment. '\
            'Node monitoring will be stopped.' % deployment.node_name)
    deployment.temp_info = deployment.state
    deployment.state = 'lost'

def collect_nodes(node_state):
    logger_compute = logging.getLogger("COMPUTE")
    cluster_desc = get_cluster_desc()
    db_session = open_session()
    pending_deployments = db_session.query(Deployment).filter_by(state = node_state).all()
    if len(pending_deployments) > 0:
        state_fct = getattr(sys.modules[__name__], '%s_fct' % node_state)
        for d in pending_deployments:
            try:
                if d.updated_at is not None:
                    last_update = datetime.datetime.strptime(str(d.updated_at), '%Y-%m-%d %H:%M:%S')
                else:
                    last_update = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                logger_compute.info("### Node '%s' enters in '%s' state at %s" %
                        (d.node_name, node_state, last_update))
                ret_fct = False
                ret_fct = state_fct(d, cluster_desc, db_session, logger_compute)
                if ret_fct == True:
                    d.updated_at = datetime.datetime.now()
                    progress_forward(d)
            except:
                logger_compute.exception("Exception in '%s' state:" % node_state)
    close_session(db_session)


# Check deployed environments
def check_ssh_is_ready(node_desc, env_desc, logger):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(node_desc.get("ip"), username=env_desc.get("ssh_user"), timeout=1.0)
        ssh.close()
        return True
    except:
        logger.warning("Could not connect to %s" % node_desc['name'])
        return False


def check_cloud9_is_ready(node_desc, env_desc, logger):
    if not 'public_ip' in node_desc:
        ret_bool = True
    else:
        ret_bool = False
        cloud9_ide_url = "http://%s/ide.html" % (node_desc.get("public_ip"))
        result = requests.get(cloud9_ide_url)
        if result.status_code == 200 and "<title>Cloud9</title>" in result.text:
            ret_bool = True
        if result.status_code == 401 and "Unauthorized" in result.text:
            ret_bool = True
        if not ret_bool:
            logger.error("%s: status code %d" % (node_desc.get("ip"), result.status_code))
    return ret_bool


# Test if the processus already exists on the remote nodes
def ps_ssh(ssh_session, process):
    try:
        (stdin, stdout, stderr) = ssh_session.exec_command("ps aux | grep %s | grep -v grep | wc -l" % process)
        return_code = stdout.channel.recv_exit_status()
        output = stdout.readlines()
        return int(output[0].strip())
    except SSHException:
        return -1


# Deploy environments
def nfs_boot_conf_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    # Create a folder containing network boot files that will be served via TFTP
    tftpboot_template_folder = "/tftpboot/rpiboot_uboot"
    tftpboot_node_folder = "/tftpboot/%s" % server["id"]
    if os.path.isdir(tftpboot_node_folder):
        shutil.rmtree(tftpboot_node_folder)
    shutil.copytree(tftpboot_template_folder, tftpboot_node_folder)
    return True


def nfs_boot_off_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    # Turn off port
    turn_off_port(server["switch"], server["port_number"])
    return True


def nfs_boot_on_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    # Turn on port
    turn_on_port(server['switch'], server["port_number"])
    return True


def env_copy_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    environment = cluster_desc['environments'][deployment.environment]
    try:
        ret_fct = False
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server.get("ip"), username="root", timeout=1.0)
        # Check the booted system is the NFS system
        (stdin, stdout, stderr) = ssh.exec_command('cat /etc/hostname')
        return_code = stdout.channel.recv_exit_status()
        myname = stdout.readlines()[0].strip()
        if myname == 'nfspi':
            # Get the path to the IMG file
            img_path = cluster_desc['img_dir'] + environment['img_name']
            logger.info("%s: copy %s to the SDCARD" % (server["name"], img_path))
            # Write the image of the environment on SD card
            deploy_cmd = "rsh -o StrictHostKeyChecking=no %s@%s 'cat %s' | tar xzOf - | \
                    pv -n -p -s %s 2> progress-%s.txt | dd of=/dev/mmcblk0 bs=4M conv=fsync &" % (
                            cluster_desc["pimaster"]["user"], cluster_desc["pimaster"]["ip"], img_path,
                            environment["img_size"], server["name"])
            (stdin, stdout, stderr) = ssh.exec_command(deploy_cmd)
            return_code = stdout.channel.recv_exit_status()
            deployment.temp_info = 0
            ret_fct = True
        else:
            logger.error('Fail to detect the NFS filesystem: wrong hostname \'%s\'' % myname)
        ssh.close()
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        updated = datetime.datetime.strptime(str(deployment.updated_at), '%Y-%m-%d %H:%M:%S')
        elapsedTime = (datetime.datetime.now() - updated).total_seconds()
        logger.warning("Could not connect to %s since %d seconds" % (server['name'], elapsedTime))
        if elapsedTime > lost_timeout:
            is_lost(deployment, logger)
    return ret_fct


def env_check_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    ret_fct = False
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server.get("ip"), username="root", timeout=1.0)
        environment = cluster_desc['environments'][deployment.environment]
        if ps_ssh(ssh, 'mmcblk0') == 0:
            ret_fct = True
        else:
            cmd = f"tail -n 1 progress-{server['name']}.txt"
            (stdin, stdout, stderr) = ssh.exec_command(cmd)
            return_code = stdout.channel.recv_exit_status()
            output = stdout.readlines()
            if len(output) == 0:
                logger.warning("%s: No progress value for the running environment copy" % server.get("ip"))
                updated = datetime.datetime.strptime(str(deployment.updated_at), '%Y-%m-%d %H:%M:%S')
                elapsedTime = (datetime.datetime.now() - updated).total_seconds()
                # Compute the progress value with an assumed transfert rate of 8 MB/s
                percent = elapsedTime * 8000000 * 100 / environment.get('img_size')
            else:
                percent = output[0].strip()
            deployment.temp_info = percent
        ssh.close()
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("Could not connect to %s" % server['name'])
    return ret_fct


def delete_partition_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server.get("ip"), username="root", timeout=1.0)
        # Register the size of the existing partition
        cmd = "rm progress-%s.txt; fdisk -l /dev/mmcblk0" % server['name']
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        output = stdout.readlines()
        # Partition size in sectors
        deployment.temp_info = int(output[-1].split()[3])
        # Delete the second partition
        cmd = "(echo d; echo 2; echo w) | fdisk -u /dev/mmcblk0"
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        ssh.close()
        return True
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("Could not connect to %s" % server['name'])
    return False


def create_partition_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    environment = cluster_desc['environments'][deployment.environment]
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server.get("ip"), username="root", timeout=1.0)
        moreMB = int(deployment.system_size)
        if moreMB == 8:
            logger.info("%s: Create a partition with the whole free space" % server['name'])
            cmd = ("(echo n; echo p; echo 2; echo '%s'; echo ''; echo w) | fdisk -u /dev/mmcblk0" %
                    environment.get("sector_start"))
        else:
            # Total size of the new partition in sectors (512B)
            moreSpace = int(deployment.temp_info) + (moreMB * 1024 * 1024 / 512)
            logger.info("%s: Create a partition with a size of %d sectors" % (server['name'], moreSpace))
            cmd = ("(echo n; echo p; echo 2; echo '%s'; echo '+%d'; echo w) | fdisk -u /dev/mmcblk0" %
                    (environment.get("sector_start"), moreSpace))
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        cmd = "partprobe"
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        ssh.close()
        return True
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("Could not connect to %s" % server['name'])
    return False


def mount_partition_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server.get("ip"), username="root", timeout=1.0)
        # Update the deployment
        cmd = "mount /dev/mmcblk0p1 boot_dir"
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        # Delete the bootcode.bin file as soon as possible
        cmd = "rm boot_dir/bootcode.bin"
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        cmd = "mount /dev/mmcblk0p2 fs_dir"
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        ssh.close()
        return True
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("Could not connect to %s" % server['name'])
    return False


def resize_partition_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server.get("ip"), username="root", timeout=1.0)
        cmd = "resize2fs /dev/mmcblk0p2 &> /dev/null &"
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        ssh.close()
        return True
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("Could not connect to %s" % server['name'])
    return False


def wait_resizing_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server.get("ip"), username="root", timeout=1.0)
        ret_fct = False
        if ps_ssh(ssh, 'resize2fs') == 0:
            ret_fct = True
        ssh.close()
        return ret_fct
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("Could not connect to %s" % server['name'])
    return False


def system_conf_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    environment = cluster_desc['environments'][deployment.environment]
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server.get("ip"), username="root", timeout=1.0)
        if environment['type'] == 'default':
            if environment['name'].startswith('raspbian'):
                # Create the ssh file in the boot partition to start SSH on startup
                cmd = "touch boot_dir/ssh"
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
                # Avoid the execution of the expand/resize script
                cmd = "sed -i 's:init=.*$::' boot_dir/cmdline.txt"
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
                # Set the hostname to modify the bash prompt
                cmd = "echo '%s' > fs_dir/etc/hostname" % server['name']
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
            if environment['name'] == 'raspbian_cloud9':
                cmd = "sed -i 's/-a :/-a admin:%s/' fs_dir/etc/systemd/system/cloud9.service" % deployment.system_pwd
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
        else:
            if environment['name'].startswith('raspbian'):
                # Set the hostname to modify the bash prompt
                cmd = "echo '%s' > fs_dir/etc/hostname" % server['name']
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
        # Copy boot files to the tftp folder
        tftpboot_node_folder = "/tftpboot/%s" % server['id']
        # Do NOT copy the *.dat files of the boot partition, they immensely slow down the raspberry
        cmd = f"scp -o 'StrictHostKeyChecking no' -r root@{server.get('ip')}:\"boot_dir/*.gz boot_dir/*.dtb \
                boot_dir/*.img boot_dir/*.txt boot_dir/overlays/\" {tftpboot_node_folder}/"
        subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Reboot to initialize the operating system
        (stdin, stdout, stderr) = ssh.exec_command("reboot")
        return_code = stdout.channel.recv_exit_status()
        ssh.close()
        return True
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("Could not connect to %s" % server['name'])
    return False


def user_conf_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    # Get the environment
    environment = cluster_desc['environments'][deployment.environment]
    # Get the user SSH key
    db_user = db_session.query(User).filter_by(id = deployment.user_id).first()
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server.get("ip"), username=environment.get("ssh_user"), timeout=1.0)
        (stdin, stdout, stderr) = ssh.exec_command('cat /etc/hostname')
        return_code = stdout.channel.recv_exit_status()
        myname = stdout.readlines()[0].strip()
        if myname == 'nfspi':
            logger.error('\'%s\' Hangs on the NFS filesystem' % server['name'])
            return False
        else:
            my_ssh_keys = ''
            if db_user.ssh_key is not None and len(db_user.ssh_key) > 0:
                my_ssh_keys = '\n%s' % db_user.ssh_key
            if deployment.public_key is not None and len(deployment.public_key) > 0:
                my_ssh_keys = '%s\n%s' % (my_ssh_keys, deployment.public_key)
            if len(my_ssh_keys) > 0:
                # Add the public key of the user
                cmd = "echo '%s' >> .ssh/authorized_keys" % my_ssh_keys
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
            if deployment.environment == 'tiny_core':
                # Change the 'tc' user password
                cmd = "echo -e '%s\n%s' | sudo passwd tc; filetool.sh -b" % (
                        deployment.system_pwd, deployment.system_pwd)
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
            if deployment.environment.startswith('raspbian'):
                # Change the 'pi' user password
                cmd = "echo -e '%s\n%s' | sudo passwd pi" % (deployment.system_pwd, deployment.system_pwd)
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
            ssh.close()
            return True
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        updated = datetime.datetime.strptime(str(deployment.updated_at), '%Y-%m-%d %H:%M:%S')
        elapsedTime = (datetime.datetime.now() - updated).total_seconds()
        logger.warning("Could not connect to %s since %d seconds" % (server['name'], elapsedTime))
        if elapsedTime > lost_timeout:
            is_lost(deployment, logger)
    return False


def user_script_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    environment = cluster_desc['environments'][deployment.environment]
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
                    if deployment.environment.startswith('raspbian'):
                        f.write("DEBIAN_FRONTEND=noninteractive\n")
                    f.write(deployment.init_script)
                ftp.put(random_file_path, "/tmp/init_script.sh")
                if "init_script.sh" in ftp.listdir("/tmp"):
                    # Launch init script
                    cmd = "touch /tmp/started_init_script; sed -i 's/\r$//' /tmp/init_script.sh; \
                            %s /tmp/init_script.sh; touch /tmp/finished_init_script" % environment.get("shell")
                    ssh.exec_command(cmd)
                else:
                    logger.error(f"\"init_script.sh\" not in /tmp")
            if "finished_init_script" in ftp.listdir("/tmp/"):
                finish_init = True
            ftp.close()
        ssh.close()
        logger.info("%s: finish_init_script: %s" % (server.get('id'), finish_init))
        no_check = True
        finish_deployment = False
        if environment.get("name") == "raspbian_cloud9":
            no_check = False
            finish_deployment = check_cloud9_is_ready(server, environment, logger)
        if no_check:
            finish_deployment = check_ssh_is_ready(server, environment, logger)
        logger.info("%s: finish_deployment: %s" % (server.get('id'), finish_deployment))
        return finish_init and finish_deployment
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("Could not connect to %s" % server['name'])
    return False


# Create environment images
def img_create_part_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    environment = cluster_desc['environments'][deployment.environment]
    logger.info("Create the image '%s' from the node '%s'" % (deployment.temp_info, server['name']))
    ret_fct = False
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server.get("ip"), username=environment.get("ssh_user"), timeout=1.0)
        cmd = "fdisk -l /dev/mmcblk0"
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        output = stdout.readlines()
        if len(output) > 10:
            logger.error("%s: More than 2 partitions detected. Can not create another partition!")
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
                logger.info('%s: nb sectors: %d, last sector: %d' % (server['name'], nb_sectors, last_sector))
                # Create a new partition that begins at (last_sector + 20 sectors)
                cmd = ("(echo n; echo ''; echo ''; echo '%d'; echo '+%d'; echo w) | fdisk -u /dev/mmcblk0" %
                        ((last_sector + 20), partition_size))
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
                # Save the end of the user partitions
                deployment.temp_info = '%s %d' % (deployment.temp_info, last_sector)
                ret_fct = True
            else:
                logger.error('%s: No enough space on the disk. Only %d sectors available, %d required sectors' %
                        (server.get('id'), (nb_sectors - last_sector), partition_size))
        ssh.close()
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("Could not connect to %s" % server['name'])
    return ret_fct


def img_format_part_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    environment = cluster_desc['environments'][deployment.environment]
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server.get("ip"), username=environment.get("ssh_user"), timeout=1.0)
        cmd = "partprobe"
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        # Get the name of the new partition
        cmd = "ls /dev/mmcblk0p*"
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        output = stdout.readlines()
        partition_name = output[-1].strip()
        logger.info("%s: Format the partition '%s'" % (server['name'], partition_name))
        cmd = "mkfs.ext4 %s &> /dev/null &" % partition_name
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        ssh.close()
        # Save the partition name
        deployment.temp_info = '%s %s' % (deployment.temp_info, partition_name)
        return True
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("Could not connect to %s" % server['name'])
    return False


def img_copy_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    environment = cluster_desc['environments'][deployment.environment]
    ret_fct = False
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server.get("ip"), username=environment.get("ssh_user"), timeout=1.0)
        end_partition = int(deployment.temp_info.split()[1])
        partition_name = deployment.temp_info.split()[2]
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
                logger.info("%s: Mount the partition '%s'" % (server.get('ip'), partition_name))
                cmd = "mount %s img_part" % partition_name
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
                mounted_part = return_code == 0
            if mounted_part:
                # Write the size of the uncompressed image file to the JSON
                env_name = deployment.temp_info.split()[0]
                env_file_path = cluster_desc['env_cfg_dir'] + env_name + '.json'
                with open(env_file_path, 'r') as jsonfile:
                    env_data = json.load(jsonfile)
                env_data['img_size'] = (end_partition + 10) * 512
                with open(env_file_path, 'w') as jsonfile:
                    json.dump(env_data, jsonfile)
                # Copy the system to the image file
                cmd = "dd if=/dev/mmcblk0 of=img_part/%s.img bs=512 count=%d &" % (env_name, end_partition + 10)
                (stdin, stdout, stderr) = ssh.exec_command(cmd)
                return_code = stdout.channel.recv_exit_status()
                ret_fct = True
                deployment.temp_info = 0
            else:
                logger.error("%s: Can not mount the partition '%s'" % (server['name'], partition_name))
        ssh.close()
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("Could not connect to %s" % server['name'])
    return ret_fct


def img_copy_check_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    environment = cluster_desc['environments'][deployment.environment]
    ret_fct = False
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server['ip'], username=environment['ssh_user'], timeout=1.0)
        if ps_ssh(ssh, 'count') == 0:
            ret_fct = True
        else:
            cmd = f"tail -n 1 progress-{server['name']}.txt"
            (stdin, stdout, stderr) = ssh.exec_command(cmd)
            return_code = stdout.channel.recv_exit_status()
            output = stdout.readlines()
            if len(output) == 0:
                logger.warning("%s: No progress value for the running image copy" % server["name"])
                updated = datetime.datetime.strptime(str(deployment.updated_at), '%Y-%m-%d %H:%M:%S')
                elapsedTime = (datetime.datetime.now() - updated).total_seconds()
                # Compute the progress value with an assumed transfert rate of 8 MB/s
                percent = elapsedTime * 8000000 * 100 / environment.get('img_size')
            else:
                percent = output[0].strip()
            deployment.temp_info = percent
        ssh.close()
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("Could not connect to %s" % server['name'])
    return ret_fct


def img_customize_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    environment = cluster_desc['environments'][deployment.environment]
    ret_fct = False
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server['ip'], username=environment['ssh_user'], timeout=1.0)
        # Get a free loop device
        cmd = 'losetup -f'
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        loop_device = stdout.readlines()[0].strip()
        logger.info("Delete the third partition by using '%s'" % loop_device)
        # Link the .img file to the loop device
        cmd = 'cd img_part; losetup -P %s *.img' % loop_device
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        # Delete the third partition
        cmd = '(echo d; echo 3; echo w) | fdisk -u %s' % loop_device
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        # Release the loop device
        cmd = 'losetup -d %s' % loop_device
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        ret_fct = True
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("Could not connect to %s" % server['name'])
    return ret_fct


def img_compress_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    environment = cluster_desc['environments'][deployment.environment]
    ret_fct = False
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server['ip'], username=environment['ssh_user'], timeout=1.0)
        # Compress the filesystem image
        cmd = "cd img_part; gzip -9 *.img &"
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        ssh.close()
        ret_fct = True
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("Could not connect to %s" % server['name'])
    return ret_fct


def img_compress_check_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    environment = cluster_desc['environments'][deployment.environment]
    ret_fct = False
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server['ip'], username=environment['ssh_user'], timeout=1.0)
        if ps_ssh(ssh, 'gzip') == 0:
            # Get both the filename and the size of the compressed image file
            cmd = "rm -f progress-{server['name']}.txt; cd img_part; ls -l *.img.gz | tail -n 1"
            (stdin, stdout, stderr) = ssh.exec_command(cmd)
            return_code = stdout.channel.recv_exit_status()
            output = stdout.readlines()[0].split()
            deployment.temp_info = '%s %s' % (output[-1], output[4])
            ret_fct = True
        else:
            cmd = f"tail -n 1 progress-{server['name']}.txt"
            (stdin, stdout, stderr) = ssh.exec_command(cmd)
            return_code = stdout.channel.recv_exit_status()
            output = stdout.readlines()
            if len(output) == 0:
                logger.warning("%s: No progress value for the running image compression" % server["name"])
                updated = datetime.datetime.strptime(str(deployment.updated_at), '%Y-%m-%d %H:%M:%S')
                elapsedTime = (datetime.datetime.now() - updated).total_seconds()
                # Compute the progress value from past experiments on Pi 3B+
                percent = elapsedTime * 1500000 * 100 / environment.get('img_size')
            else:
                percent = output[0].strip()
            deployment.temp_info = percent
        ssh.close()
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        logger.warning("Could not connect to %s" % server['name'])
    return ret_fct


def img_upload_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    environment = cluster_desc['environments'][deployment.environment]
    img_name = deployment.temp_info.split()[0]
    img_size = deployment.temp_info.split()[1]
    logger.info("Upload the file '%s' from the node '%s'" % (img_name, server['name']))
    cmd = f"""rsh -o "StrictHostKeyChecking no" %s@%s "cat img_part/%s" | \
                pv -n -p -s %s 2> /tmp/progress-{server['name']}.txt | dd of=%s%s bs=4M conv=fsync &""" % (
                        environment['ssh_user'], server['ip'], img_name, img_size,
                        cluster_desc['img_dir'], img_name)
    subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deployment.temp_info = 0
    return True


def upload_check_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    cmd = "ps aux | grep %s | grep -v grep | wc -l" % server['ip']
    process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    nb_line = process.stdout.decode('utf-8').strip()
    if int(nb_line) == 0:
        cmd = f"rm progress-{server['name']}.txt"
        (stdin, stdout, stderr) = ssh.exec_command(cmd)
        return_code = stdout.channel.recv_exit_status()
        # Load the new environement to the cluster description
        load_cluster_desc()
        return True
    else:
        cmd = f"tail -n 1 /tmp/progress-{server['name']}.txt"
        process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        output = process.stdout.decode('utf-8').strip()
        if len(output) == 0:
            logger.warning("%s: No progress value for the running environment copy" % server.get("ip"))
            updated = datetime.datetime.strptime(str(deployment.updated_at), '%Y-%m-%d %H:%M:%S')
            elapsedTime = (datetime.datetime.now() - updated).total_seconds()
            # Compute the progress value with an assumed transfert rate of 8 MB/s
            percent = elapsedTime * 8000000 * 100 / environment.get('img_size')
        else:
            percent = output
        deployment.temp_info = percent
    return False


# Hard Reboot nodes (off -> on -> check SSH)
def off_requested_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    # Turn off port
    turn_off_port(server["switch"], server["port_number"])
    return True


def on_requested_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    # Turn off port
    turn_on_port(server["switch"], server["port_number"])
    return True


def rebooting_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    environment = cluster_desc['environments'][deployment.environment]
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        if use_env_ssh_user(deployment.temp_info):
            ssh.connect(server.get("ip"), username=environment.get("ssh_user"), timeout=1.0)
        else:
            ssh.connect(server.get("ip"), username="root", timeout=1.0)
        ssh.close()
        return True
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        updated = datetime.datetime.strptime(str(deployment.updated_at), '%Y-%m-%d %H:%M:%S')
        elapsedTime = (datetime.datetime.now() - updated).total_seconds()
        logger.info("Could not connect to %s since %d seconds" % (server['name'], elapsedTime))
        if elapsedTime > lost_timeout:
            is_lost(deployment, logger)
    return False


# Destroying deployments
def destroy_request_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    if deployment.environment is not None:
        environment = cluster_desc['environments'][deployment.environment]
        # Remove the bootcode.bin file that can appear after updating the Raspbian OS
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server.get("ip"), username=environment.get("ssh_user"), timeout=1.0)
            (stdin, stdout, stderr) = ssh.exec_command('rm /boot/bootcode.bin && sync')
            return_code = stdout.channel.recv_exit_status()
            ssh.close()
        except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
            logger.warning('No SSH connection: can not try to delete the bootcode.bin file')
    # Turn off port
    turn_off_port(server["switch"], server["port_number"])
    # Delete the tftpboot folder
    tftpboot_node_folder = "/tftpboot/%s" % server["id"]
    if os.path.isdir(tftpboot_node_folder):
        shutil.rmtree(tftpboot_node_folder)
    return True


def destroying_fct(deployment, cluster_desc, db_session, logger):
    # Get description of the server that will be deployed
    server = cluster_desc['nodes'][deployment.node_name]
    can_connect = True
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(server.get("ip"), username="root", timeout=1.0)
        ssh.close()
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as e:
        can_connect = False
    return not can_connect
