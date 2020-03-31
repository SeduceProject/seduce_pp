#!/bin/bash

# Variables to edit
SWITCH_IP="192.168.1.23"
NETWORK_IP="192.168.1"
# Ask for the first IP to use
INC_IP="20"
DB_ROOT_PWD="CHANGE_ME_ROOT"
DB_USER_PWD="CHANGE_ME_USER"
INTERFACE="eth0"
NB_PORT="8"

# Common variables
SNMP_OID="1.3.6.1.2.1.105.1.1.1.3.1"
ON="1"
OFF="2"
# Default value should be ""
PORTS="2 21"

if [ -z "$PORTS" ]; then
    PORTS=$(seq 1 $NB_PORT)
fi

echo "# Update raspbian system"
apt update && apt -y dist-upgrade

echo "# Install the required packages"
apt install -y dnsmasq git libffi-dev mariadb-client mariadb-server nfs-kernel-server \
    pv python3-mysqldb python3-pip snmp tshark vim

echo "# Stop services"
service dnsmasq stop
service nfs-kernel-server stop

echo "# Clone the git repository"
if [ ! -d /root/seduce_pp ]; then
    git clone http://github.com/remyimt/seduce_pp
    cd seduce_pp
    pip3 install -r requirements.txt
fi
cd /root/seduce_pp/autoconf

echo "# Create the dnsmasq configuration"
MASTER_IP=$(ifconfig | grep -A 1 eth0 | grep inet | awk '{ print $2}')
echo " +  Add my IP '$MASTER_IP' to the dnsmasq configuration"
cp files/dnsmasq.conf.default dnsmasq.conf
sed -i "s/PIMASTERIP/$MASTER_IP/" dnsmasq.conf
echo "dhcp-range=$NETWORK_IP.0,static,255.255.255.0" >> dnsmasq.conf

echo "# Register the pimaster (me) to the cluster configuration"
cp files/main.json .
sed -i "s/PIMASTERIP/$MASTER_IP/" main.json
sed -i "s/SWITCHIP/$SWITCH_IP/" main.json
mv main.json ../cluster_desc

echo "# Turn off all nodes connected to $SWITCH_IP"
for p in $PORTS; do
    snmpset -v2c -c private $SWITCH_IP $SNMP_OID.$p i $OFF
done
sleep 1
echo "# Detecting MAC addresses"
for p in $PORTS; do
    echo " + Turn on the node on port $p"
    snmpset -v2c -c private $SWITCH_IP $SNMP_OID.$p i $ON
    sleep 5
    echo " + Capturing PXE boot requests"
    tshark -nni eth0 -w port.pcap -a duration:10 port 67 and 68
    echo " + Analyzing captured requests"
    mac=$(tshark -r port.pcap -Y "bootp.option.type == 53 and bootp.ip.client == 0.0.0.0"\
        -T fields -e frame.time -e bootp.ip.client -e bootp.hw.mac_addr |\
        awk '{ print $7 }' | uniq)
    echo $mac
    if [ $(echo $mac | wc -l) -eq 1 ]; then
        echo "  - MAC node on port $p: $mac"
        node_ip=$NETWORK_IP.$(( $p + $INC_IP))
        echo "  - Associated the MAC address to $node_ip"
        echo "dhcp-host=$mac,node-$p,$node_ip" >> dnsmasq.conf
        echo "  - Create the cluster configuration associated to 'node-$p'"
        node_file="../cluster_desc/nodes/node-$p.json"
        if [ $p -lt 10 ]; then
            json_file="files/node-default.json"
        else
            json_file="files/node-default10.json"
        fi
        cp $json_file $node_file
        sed -i "s/NODENAME/node-$p/" $node_file
        sed -i "s/NODEPORT/$p/" $node_file
        sed -i "s/NODEIP/$node_ip/" $node_file
    else
        echo "  - Failed to retrieve the MAC address for the node on port $p"
    fi
    echo " + Turn off the node on port $p"
    snmpset -v2c -c private $SWITCH_IP $SNMP_OID.$p i $OFF
done
rm -f port.pcap

echo "# Move configuration files to /etc"
mv dnsmasq.conf /etc/
cp files/exports /etc/

if [ ! -d /root/environments ]; then
    echo "# Copy the environments"
    mkdir /root/environments
    cp files/*.img.gz /root/environments
fi

if [ ! -d /nfs ]; then
    echo "# Configure the NFS"
    echo " + Extract the NFS file system"
    tar xf files/nfs.tar.gz -C /
    echo " + Generate SSH keys"
    ssh-keygen -f /root/.ssh/id_rsa -t rsa -N ''
    echo " + Copy SSH keys to the NFS"
    cat /root/.ssh/id_rsa.pub > /nfs/raspi/root/.ssh/authorized_keys
    # WARNING: SSH keys for the NFS file system are missing, you have to generate them
    #          then copy the public key to the pimaster /root/.ssh/authorized_keys
fi

if [ ! -d /tftpboot ]; then
    echo "# Configure the PXE server"
    tar xf files/tftpboot.tar.gz -C /
    echo "nfsroot=$MASTER_IP:/nfs/raspi,udp,v3 rw ip=dhcp root=/dev/nfs rootwait \
        console=tty1 console=ttyAMA0,115200" > /tftpboot/rpiboot_uboot/cmdline.txt
fi

echo "# Configure the pimaster (me) as the network gateway"
echo 'net.ipv4.ip_forward=1' > /etc/sysctl.conf
sysctl -p /etc/sysctl.conf
echo 'pimaster' > /etc/hostname

mysql -e "SHOW DATABASES" &> /dev/null
if [ $? -eq 0 ]; then
    echo '# Configure the mysql server'
    # Make sure that NOBODY can access the server without a password
    mysql -e "UPDATE mysql.user SET Password = PASSWORD('$DB_ROOT_PWD') WHERE User = 'root'"
    # Delete anonymous users
    mysql -e "DELETE FROM mysql.user WHERE User='';"
    # Ensure the root user can not log in remotely
    mysql -e "DELETE FROM mysql.user WHERE User='root' AND Host NOT IN ('localhost', '127.0.0.1', '::1');"
    # Kill off the demo database
    mysql -e "DROP DATABASE test"
    mysql -e "DELETE FROM mysql.db WHERE Db='test' OR Db='test\_%'"
    # Create the database
    mysql -e "CREATE DATABASE piseduce"
    # Create the user 'pipi'
    mysql -e "CREATE USER 'pipi'@'localhost' IDENTIFIED BY '$DB_USER_PWD'"
    # Grant access to the database
    mysql -e "GRANT USAGE ON *.* TO 'pipi'@localhost IDENTIFIED BY '$DB_USER_PWD';"
    mysql -e "GRANT USAGE ON *.* TO 'pipi'@'%' IDENTIFIED BY '$DB_USER_PWD';"
    mysql -e "GRANT ALL PRIVILEGES ON piseduce.* TO 'pipi'@'localhost';"
    # Make our changes take effect
    mysql -e "FLUSH PRIVILEGES"
fi

echo "# Node first boot"
echo " + Start services"
service dnsmasq restart
service nfs-kernel-server restart
echo " + Prepare tftpboot files"
cp -r /tftpboot/rpiboot_uboot/* /tftpboot/
echo " + Turn on all nodes"
for p in $PORTS; do
    echo "  - Turn on the node on port $p"
    snmpset -v2c -c private $SWITCH_IP $SNMP_OID.$p i $ON
done
echo " + Waiting 30s for the nodes"
sleep 30
for p in $PORTS; do
    echo " + SSH connection to 'node-$p'"
    node_ip=$NETWORK_IP.$(( $p + $INC_IP))
    SSH_OK=""
    while [ -z "$SSH_OK" ]; do
        ssh -o StrictHostKeyChecking=no $node_ip 'echo ""'
        if [ $? -eq 0 ]; then
            echo "  - SSH: OK"
            SSH_OK="yes"
        else
            echo "  - SSH connection failed to '$node_ip'"
        fi
        sleep 5
    done
    echo " + Get the node identifier"
    node_id=$(ssh -o StrictHostKeyChecking=no $node_ip "cat /proc/cpuinfo" | \
        grep "Serial" | awk '{ print substr( $3, length($3) - 7, length($3) ) }')
    node_file="../cluster_desc/nodes/node-$p.json"
    sed -i "s/NODEID/$node_id/" $node_file
done
echo " + Turn off all nodes"
for p in $PORTS; do
    echo "  - Turn off the node on port $p"
    snmpset -v2c -c private $SWITCH_IP $SNMP_OID.$p i $OFF
done
echo " + Clean the tftpboot directory"
for f in $(ls /tftpboot/rpiboot_uboot); do
    rm -rf /tftpboot/$f
done

echo "# Configure piSeduce services"
cp ../admin/*.service /etc/systemd/system/
systemctl enable pitasks.service
systemctl enable pifrontend.service

echo "# Reboot the node in 20 seconds"
sleep 20 && reboot
