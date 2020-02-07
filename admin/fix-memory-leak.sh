#!/bin/bash

echo "### $(date) Before restarting ###" &>> /tmp/mem-process-info
top -bn3 -o %MEM | sed -e '1,6d' | head -6 &>> /tmp/mem-process-info
/usr/local/bin/supervisorctl stop frontend
sleep 3
/usr/local/bin/supervisorctl start frontend
sleep 10
echo "### $(date) After the restart ###" &>> /tmp/mem-process-info
top -bn3 -o %MEM | sed -e '1,6d' | head -6 &>> /tmp/mem-process-info
