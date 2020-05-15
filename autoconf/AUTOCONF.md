## Required files
* Raspbian buster image file: __2020-02-13-raspbian-buster-lite.img__
* Archive of the NFS file system: __nfs.tar.gz__
* Archive of the tftpboot directory: __tftpboot.tar.gz__

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

## Umount the raspbian buster image
* Umount the image
```
sudo umount mount_dir
sudo losetup -d /dev/loop1
```

## Configure the raspbian to the first PiSeduce boot
* Decompress files to the image
```
sudo tar xf archive_files/tftpboot.tar.gz -C mount_dir/
sudo tar xf archive_files/nfs.tar.gz -C mount_dir/
```

* Update the system

## Enable mDNS
* Edit the file `/etc/avahi/avahi-daemon.conf`
```
[reflector]
enable-reflector=yes
reflect-ipv=yes
```
* Restart the avahi daemon: `service avahi-daemon restart`

## First PiSeduce Boot: Configure your own cluster
#### Switch Configuration
* Configure the switch SNMP access
* Test the switch SNMP connection

#### Raspberry Pi 4 Configuration
* Write the Raspbian image on the SD_CARD
* Open the first partition of the SD_CARD - the `boot` partition - and create an empty file called `ssh`
* Boot the Raspberry Pi from the SD_CARD
* Update the system: `sudo apt update && sudo apt -y dist-upgrade`
* Send the file `pieeprom_2020_05_14.bin` via `scp`
* Update the EEPROM: `rpi-eeprom-update -d -f pieeprom_2020_05_14.bin`
* Reboot the Raspberry Pi
* The Raspberry is ready to integrate the PiCluster
* source [here](https://www.raspberrypi.org/documentation/hardware/raspberrypi/bcm2711_bootloader_config.md)

#### PiMaster Configuration
* If you want to configure the pimaster network from DHCP, customize the piseduce image file
* Write the image file to the SD_CARD
* Boot the pimaster Raspberry Pi
* Connect to http://pimaster.local:9000

