#!/bin/bash

CONFIG="/home/pipi/seduce_pp/cluster_desc/nodes/"

echo "Enter the id of the node:"
echo -n "$: "
read ID
NAME=$(grep 071f11f3 $CONFIG/* | cut -d ':' -f1)
if [ -z "$NAME" ]; then
    echo "Unknown id '$ID' from the configuration '$CONFIG'"
else
    NAME=$(basename $NAME | cut -d '.' -f1)
    echo $ID: $NAME
fi
