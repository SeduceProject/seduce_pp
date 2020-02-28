#!/bin/bash

CONFIG="/home/pipi/seduce_pp/lib/config/cluster_config.py"
CMDLINE_DIR="/home/pipi/seduce_pp/admin"

echo "Enter the id of the node:"
echo -n "$: "
read ID
NAME=$(grep -B 2 "\"$ID\"" $CONFIG | grep "name" | sed 's: *::g' | cut -d '"' -f4)
echo $ID: $NAME
