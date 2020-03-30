#!/bin/bash

CONFIG="/home/pipi/seduce_pp/cluster_desc/nodes"

echo "Enter the name of the node:"
echo -n "$: "
read NAME
NODE_DESC="$CONFIG/$NAME.json"
if [ -e $NODE_DESC ]; then
    ID=$(cat $CONFIG/$NAME.json | grep "id" | sed 's: *::g' | cut -d '"' -f4)
    echo $NAME: $ID
else
    echo "No description file '$NODE_DESC' for the node '$NAME'"
fi
