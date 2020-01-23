#!/bin/bash
USER=pipi
PWD=piseduce
DB_NAME=piseduce_remy
NAME="node-21"
NEW_STATE="created"

echo "Name of the node:"
echo -n "!! "
read NAME
id=$(grep -A 2 $NAME lib/config/cluster_config.py | grep id | sed 's/.*"\(.*\)",$/\1/')
STATE=$(mysql -u$USER -p$PWD $DB_NAME -Ne "SELECT state FROM deployment WHERE state != 'destroyed' AND server_id = '$id';")
echo "New state (current=$STATE):"
echo -n "!! "
read NEW_STATE

echo $id
if [ ! -z "$id" ]; then
  mysql -u$USER -p$PWD $DB_NAME -e "UPDATE deployment SET state='$NEW_STATE' WHERE state != 'destroyed' AND server_id = '$id';"
fi

