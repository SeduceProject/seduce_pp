#!/bin/bash

CONFIG="/home/pipi/seduce_pp/lib/config/cluster_config.py"
CMDLINE_DIR="/home/pipi/seduce_pp/admin"

echo "Enter the name of the node:"
echo -n "$: "
read NAME
ID=$(grep -A 3 "\"$NAME\"" $CONFIG | grep "id" | sed 's: *::g' | cut -d '"' -f4)
echo $NAME: $ID
