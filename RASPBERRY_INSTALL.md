### From 2020-02-13-raspbian-buster-lite.img
* Update the system
```
apt update && apt -y dist-upgrade
apt install pv vim
echo 'net.ipv4.ip_forward=1' > /etc/sysctl.conf
sysctl -p /etc/sysctl.conf
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
vi /etc/hosts
exit
cat /nfs/raspi/root/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys
umount dev sys proc
```

### Install the software stack
```
apt install dnsmasq git libffi-dev mariadb-client mariadb-server nfs-kernel-server python3-mysqldb python3-pip snmp
```

### Copy the updated files in the tftpboot directory
* From the tftp server:
```
cd /tftpboot/1760325b
scp -r -o StrictHostKeyChecking=no 192.168.1.62:"/boot/*.gz /boot/*.dtb /boot/*.txt /boot/*.img /boot/overlays/" .
```

### Prepare PXE boot
* Create the TFTP directory: `mkdir /tftpboot`
* Copy the files
```
/tftpboot/boocode.bin
/tftpboot/rpiboot_uboot/
```
* /tftpboot/rpiboot_uboot/cmdline.txt:
  * `nfsroot=192.168.1.62:/nfs/raspi,udp,v3 rw ip=dhcp root=/dev/nfs rootwait console=tty1 console=ttyAMA0,115200`

### Write the new hostname
* Edit `/etc/hostname`, `/etc/hosts`

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

### Configure seduce_cp
* Clone the repository: `git clone https://github.com/remyimt/seduce_pp`
* Download the environment images to /root/environements/
* Edit lib/config/cluster_config.py

### Create the systemD services
* Configure the user in both `admin/tasks.service` and `admin/frontend.service`
* Copy the service files
```
cp admin/*.service /etc/systemd/system/
systemctl enable tasks.service
systemctl enable frontend.service
service frontend start
service tasks start
```

### Create the tiny core user data
* Deploy the tiny core environment then log into with the default password 'piCore'
* Copy the public SSH key of the controller to `/home/tc/.ssh/authorized_keys`
* Backup the SSH key `filetool.sh -b`
* Copy the backup to the controller `scp tc@192.168.1.203:/mnt/mmcblk0p2/tce/mydata.tgz /nfs/raspi/`

### Note
* chemin NFS dans le rpi_uboot, retirer le chemin dans tasks/compute.py

### Download test
* Server Dell
```
.img
    10 noeuds -> best: 136s
                worst: 196s
```
* Raspberry pi 3+
```
.zip
    1 noeud  -> 203: 136

    3 noeuds -> 203: 133
                204: 273
                205: 279

    3 noeuds -> 206: 143
                207: 250
                208: 362

    6 noeuds -> 203: 183
                204: 264
                205: 225
                206: 189
                207: 189
                208: 224
.img
    3 noeuds -> 203: 364
                204: 493
                205: 547

    3 noeuds -> 206: 371
                207: 385
                208: 370
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
