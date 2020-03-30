#!/bin/bash
USER=pipi
PWD=piseduce
DB_NAME=piseduce
NAME="node-21"
NEW_STATE="created"

echo "Name of the node:"
echo -n "!! "
read NAME
STATE=$(mysql -u$USER -p$PWD $DB_NAME -Ne \
    "SELECT state FROM deployment WHERE state != 'destroyed' AND node_name = '$NAME';")
if [ -z "$STATE" ]; then
    echo "No node '$NAME' in current deployments!"
    exit 2
fi
echo "New state for the node '$NAME' (current=$STATE):"
echo -n "!! "
read NEW_STATE

mysql -u$USER -p$PWD $DB_NAME -e \
    "UPDATE deployment SET state='$NEW_STATE' WHERE state != 'destroyed' AND node_name = '$NAME';"
