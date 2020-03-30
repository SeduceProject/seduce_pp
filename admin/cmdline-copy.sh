#!/bin/bash

CONFIG="/home/pipi/seduce_pp/cluster_desc/nodes"
TFTP_DIR="/tftpboot"

if [ -z "$1" ]; then
    echo "./cmdline.sh [nfs | disk]"
    exit 2
fi
echo "WARNING: This script does not work with 'tinycore' environments!"
echo "Enter the name of the node:"
echo -n "$: "
read NAME
ID=$(cat $CONFIG/$NAME.json | grep "id" | sed 's: *::g' | cut -d '"' -f4)
if [ $(echo $ID | wc -m) -eq 9 ]; then
    echo "Id of the node '$NAME': $ID"
    if [ "$1" == "nfs" ]; then
        echo "Configuring '$NAME:$ID' for NFS boot"
        cp $TFTP_DIR/rpiboot_uboot/cmdline.txt $TFTP_DIR/$ID/cmdline.txt
        exit 0
    fi
    if [ "$1" == "disk" ]; then
        echo "Configuring '$NAME:$ID' to boot from its disk"
        echo "console=serial0,115200 console=tty1 root=PARTUUID=738a4d67-02 rootfstype=ext4 \
            elevator=deadline fsck.repair=yes rootwait quiet" > $TFTP_DIR/$ID/cmdline.txt
        exit 0
    fi
    echo "Wrong parameter. Use 'nfs' or 'disk'!"
else
    echo "Too many nodes:"
    echo $ID
fi

