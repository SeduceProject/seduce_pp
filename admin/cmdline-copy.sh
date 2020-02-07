#!/bin/bash

CONFIG="/home/pipi/seduce_pp/lib/config/cluster_config.py"
CMDLINE_DIR="/home/pipi/seduce_pp/admin"

echo "Enter the name of the node:"
echo -n "$: "
read NAME
ID=$(grep -A 3 "\"$NAME\"" $CONFIG | grep "id" | sed 's: *::g' | cut -d '"' -f4)
if [ $(echo $ID | wc -m) -eq 9 ]; then
    echo "Id of the node '$NAME': $ID"
    if [ "$1" == "nfs" ]; then
        echo "Configuring '$NAME' for NFS boot"
        cp $CMDLINE_DIR/nfs_cmdline.txt /tftpboot/$ID/cmdline.txt
        exit 0
    fi
    if [ "$1" == "disk" ]; then
        echo "Configuring '$NAME' to boot from its disk"
        cp $CMDLINE_DIR/partition_cmdline.txt /tftpboot/$ID/cmdline.txt
        exit 0
    fi
    echo "Wrong parameter. Use 'nfs' or 'disk'!"
else
    echo "Too many nodes:"
    echo $ID
fi

