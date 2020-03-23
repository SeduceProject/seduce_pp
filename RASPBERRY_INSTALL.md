#### Installation guide of the PiMaster
### From 2020-02-13-raspbian-buster-lite.img
* Update the system of the PiMaster
```
apt update && apt -y dist-upgrade
apt install pv vim
```

### Prepare NFS boot filesystem
* Create the filesystem from the an existing Raspberry Pi system
```
mkdir -p /nfs/raspi
rsync -xa --progress --exclude /nfs / /nfs/raspi
cat /root/.ssh/id_rsa.pub > /nfs/raspi/root/.ssh/authorized_keys
cd /nfs/raspi
mount --bind /dev dev
mount --bind /sys sys
mount --bind /proc proc
chroot .
echo '' > /etc/fstab
rm /etc/ssh/ssh_host_*
dpkg-reconfigure openssh-server
ssh-keygen
mkdir /root/boot_dir /root/fs_dir
echo 'nfspi' > /etc/hostname
exit
cat /nfs/raspi/root/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys
umount dev sys proc
```

### Configure the PiMaster as the network gateway
* Enable IP forwarding
```
echo 'net.ipv4.ip_forward=1' > /etc/sysctl.conf
sysctl -p /etc/sysctl.conf
```

### Install the software stack
```
apt install dnsmasq git libffi-dev mariadb-client mariadb-server nfs-kernel-server python3-mysqldb python3-pip snmp
```

### Prepare PXE boot
* Create the TFTP directory: `mkdir /tftpboot`
* Extract the rpiboot files: `tar xf tftpboot_init.tar.gz`
* Copy the files to the tftpboot folder
```
cp -r tftpboot_init/* /tftpboot/
```
* Edit `/tftpboot/rpiboot_uboot/cmdline.txt` to configure the NFS boot:
```
nfsroot=192.168.1.62:/nfs/raspi,udp,v3 rw ip=dhcp root=/dev/nfs rootwait console=tty1 console=ttyAMA0,115200
```

### Write the new hostname
* `echo 'pimaster' > /etc/hostname`

### Configure the NFS server
* /etc/exports: `/nfs *(rw,sync,no_subtree_check,no_root_squash)`
```
exportfs -a
service nfs-kernel-server restart
showmount -e
```

### Configure dnsmasq
* /etc/dnsmasq.conf
```
listen-address=192.168.1.62
interface=eth0
bind-interfaces
log-dhcp
enable-tftp
dhcp-boot=/bootcode.bin
tftp-root=/tftpboot
pxe-service=0,"Raspberry Pi Boot"
tftp-no-blocksize
no-hosts

dhcp-range=192.168.1.0,static,255.255.255.0
dhcp-option=23,64

dhcp-host=b8:27:eb:b9:70:4c,raspi4,192.168.1.124
dhcp-host=b8:27:eb:1a:30:c2,raspi5,192.168.1.125
```

### Configure the database
* Configure the root access
```
mysql_secure_installation
mysql -u root -p
```
* Configure the user access
```
CREATE DATABASE piseduce;
CREATE USER 'pipi'@'localhost' IDENTIFIED BY 'totopwd';
GRANT USAGE ON *.* TO 'pipi'@localhost IDENTIFIED BY 'totopwd';
GRANT USAGE ON *.* TO 'pipi'@'%' IDENTIFIED BY 'totopwd';
GRANT ALL PRIVILEGES ON piseduce.* TO 'pipi'@'localhost';
```

### Configure seduce_pp
* Clone the repository: `git clone https://github.com/remyimt/seduce_pp`
* Download the environment images to /root/environements/
* Edit lib/config/cluster_config.py

### Create the systemD services
* Configure the user in both `admin/tasks.service` and `admin/frontend.service`
* Copy the service files
```
cp admin/*.service /etc/systemd/system/
systemctl enable pitasks.service
systemctl enable pifrontend.service
service pifrontend start
service pitasks start
```

### Create the tiny core user data
* Get a tiny_core running node:
    - deploy the tiny_core environment on a raspberry Pi
    - wait for the node enters in the 'user_conf' state
    - connect to the node with the user 'tc' and the default password 'piCore'
* Copy the public SSH key of the pimaster to `/home/tc/.ssh/authorized_keys`
* Backup tinycore environment with the pimaster SSH key: `filetool.sh -b`
* Copy the backup to the pimaster. From the pimaster, execute:
```
scp tc@192.168.1.203:/mnt/mmcblk0p2/tce/mydata.tgz /nfs/raspi/
```

### Delete bootcode.bin of system images
```
# Get the first loop device available
sudo losetup -f
# Mount the image file
sudo losetup -P /dev/loop3 2019-09-26-raspbian-buster-lite.img
sudo mount /dev/loop3p1 mount_dir/
# Delete the bootcode.bin
sudo rm mount_dir/bootcode.bin
# Free the loop device
sudo umount mount_dir
sudo losetup -d /dev/loop3
```
