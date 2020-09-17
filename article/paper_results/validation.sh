#!/bin/bash
if [ "$1" == '-h' ]; then
    echo 'Safe usage (show results): ./validation.sh "RPI4_32_SDCARD/16_nodes_RPI4_20_09_1*"'
    echo 'Usage (show and delete files): ./validation.sh "RPI4_32_SDCARD/16_nodes_RPI4_20_09_1*" 10'
    exit
fi

falsy=$(grep -c 'ping": false' $1)
for line in $falsy; do
    path=$(echo $line | cut -d':' -f1)
    nb=$(echo $line | cut -d':' -f2)
    if [ $nb -gt 6 ]; then
        echo "$nb - $path"
    fi
    if [ -n "$2" ]; then
        if [ $nb -ge $2 ]; then
            rm $path
        fi
    fi
done
