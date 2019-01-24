def get_nfs_boot_cmdline():
    return """dwc_otg.lpm_enable=0 console=serial0,115200 console=tty1 root=/dev/nfs nfsroot=%(controller_ip)s:/nfs/raspi1,udp,v3 rw ip=dhcp rootwait elevator=deadline rootfstype=nfs"""


def get_sdcard_resize_boot_cmdline():
    return """dwc_otg.lpm_enable=0 console=serial0,115200 console=tty1 root=/dev/mmcblk0p2 rootfstype=ext4 elevator=deadline fsck.repair=yes rootwait quiet init=/usr/lib/raspi-config/init_resize.sh"""


def get_sdcard_boot_cmdline():
    return """dwc_otg.lpm_enable=0 console=serial0,115200 console=tty1 root=PARTUUID=%(partition_uuid)s rootfstype=ext4 elevator=deadline fsck.repair=yes rootwait"""
