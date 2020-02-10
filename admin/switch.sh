#!/bin/bash

PORT=17
if [ -z "$1" ]; then
    echo "This is only commands for documentation; do not run this script!"
    exit 666
fi
# Get the power state of the port 17
snmpget -v2c -c private 192.168.1.23 1.3.6.1.2.1.105.1.1.1.3.1.$PORT
# Turn off the port 17
snmpset -v2c -c private 192.168.1.23 1.3.6.1.2.1.105.1.1.1.3.1.$PORT i 2
sleep 5
# Turn on the port 17
snmpset -v2c -c private 192.168.1.23 1.3.6.1.2.1.105.1.1.1.3.1.$PORT i 1
