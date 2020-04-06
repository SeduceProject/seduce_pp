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

## First PiSeduce Boot: Configure your own cluster
