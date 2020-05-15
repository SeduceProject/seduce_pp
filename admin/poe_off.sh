#!/bin/bash

CONFIG="./cluster_desc/main.json"
# Number of POE ports of the switch
NB_PORTS=8

echo "Enter the port number of the pimaster:"
echo -n "$: "
read PI_MASTER
if [ -e $CONFIG ]; then
    IP=$(cat $CONFIG | grep -A 4 'switch' | grep 'ip' | sed 's: *::g' | cut -d '"' -f4)
    COMMUNITY=$(cat $CONFIG | grep 'snmp_community' | sed 's: *::g' | cut -d '"' -f4)
    OID_BASE=$(cat $CONFIG | grep 'snmp_oid' | sed 's: *::g' | cut -d '"' -f4)
    OID_OFFSET=$(cat $CONFIG | grep 'snmp_oid_offset' | sed 's/[ :]*//g' | cut -d '"' -f3)
    for i in $(seq 1 $NB_PORTS ); do
        if [ $i -ne $PI_MASTER ]; then
            echo "Turn off the port $i"
            snmpset -v2c -c $COMMUNITY $IP  ${OID_BASE}.$(($OID_OFFSET + $i)) i 2
        fi
    done
else
    echo "No description file '$CONFIG'"
fi
