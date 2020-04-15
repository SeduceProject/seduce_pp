## Required files
* Raspbian buster image file: __2020-02-13-raspbian-buster-lite.img__
* Archive of the NFS file system: __nfs.tar.gz__
  * You can build this archive by following the process described [here](../README.md#prepare-nfs-boot-filesystem)
  * At the end, create the archive with `tar czf nfs.tar.gz /nfs/raspi`
* Archive of the tftpboot directory: __tftpboot.tar.gz__ [download link](https://github.com/remyimt/imt-piseduce-conf/blob/master/tftpboot.tar.gz)
* __WARNING__: To [configure the raspbian system](#configure-the-raspbian-system), you must mount the system on a raspbian operating system

## Customize the raspbian buster image
* Append zeros to the image file
```
dd if=/dev/zero bs=1M count=2300 >> 2020-02-13-raspbian-buster-lite.img
```
* Expand the partition
```
fdisk -u 2020-02-13-raspbian-buster-lite.img
p; d; 2; n; p; 2; first_sector; ''; w;
```
* Mount the partition
```
sudo losetup -f
sudo losetup -P /dev/loop1 2020-02-13-raspbian-buster-lite.img
sudo mount /dev/loop1p2 mount_dir/
```
* Resize the partition
```
sudo resize2fs /dev/loop1p2
```

## Copy files to the SDCARD
* Copy NFS and PXE files
```
sudo tar xf archive_files/tftpboot.tar.gz -C mount_dir/
sudo tar xf archive_files/nfs.tar.gz -C mount_dir/
```
* Clone the seduce_pp repository
```
git clone http://github.com/remyimt/seduce_pp mount_dir/root/seduce_pp
```
* Copy the compressed raspbian image
```
mkdir mount_dir/root/environments
cp 2020-02-13-raspbian-buster-lite.img.gz mount_dir/root/environments
```
* Change the hostname
```
echo 'pimaster' > mount_dir/etc/hostname
```

## Configure the raspbian system
* __WARNING__: For this section, you must mount the system on a raspbian operating system
* chroot to the new operating system
```
chroot mount_dir
```
* Update the raspbian system and install packages
```
apt update && apt -y dist-upgrade
apt install -y dnsmasq git libffi-dev mariadb-client mariadb-server nfs-kernel-server \
  pv python3-mysqldb python3-pip snmp tshark vim
```
* Configure seduce_pp
```
cd /root/seduce_pp
pip3 install -r requirements.txt
cp admin/*.service /etc/systemd/system/
systemctl enable pitasks.service
systemctl enable pifrontend.service
```
* Configure the NFS server by creating the file **/etc/exports**
```
/nfs *(rw,sync,no_subtree_check,no_root_squash)
```
* Configure SSH connections
```
ssh-keygen -f /root/.ssh/id_rsa -t rsa -N ''
cat /root/.ssh/id_rsa.pub > /nfs/raspi/root/.ssh/authorized_keys
cat /nfs/raspi/root/.ssh/id_rsa.pub > /root/.ssh/authorized_keys
```
* Configure the vim editor by editing **/root/.vimrc**
```
set expandtab
set tabstop=4
:retab
set shiftwidth=4
set autoindent
set smartindent
set nu
set textwidth=120
set wrap
set linebreak
syntax on
filetype plugin indent on
set mouse-=a
```
* Configure the default editor (for commands as 'visudo')
```
update-alternatives --config editor
```
* Do not try to resolve the hostname while executing 'sudo' commands
```
visudo
Defaults    !fqdn
```
* Configure the avahi daemon by editing `/etc/avahi/avahi-daemon.conf`
```
[reflector]
enable-reflector=yes
reflect-ipv=yes
```
* Configure the node as a gateway
```
echo 'net.ipv4.ip_forward=1' > /etc/sysctl.conf
```
* Set the static IP (or skip the end of the section to use DHCP)
```
cd /root/seduce_pp
cp autoconf/files/dhcpcd.conf_static /etc/dhcpcd.conf
```
* Edit the file **/etc/dhcpcd.conf** to configure the network (here, the IP is 192.168.1.4)
```
static ip_address=192.168.1.4/24
static routers=192.168.1.1
static domain_name_servers=192.168.1.1
```
* Exit the chroot
```
exit
```

## Umount the raspbian buster image
* Umount the image
```
sudo umount mount_dir
sudo losetup -d /dev/loop1
```
