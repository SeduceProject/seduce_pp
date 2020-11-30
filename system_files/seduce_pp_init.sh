#!/bin/bash

## PiSeduce Configuration ##
# Detect the first boot from the MySQL database 'piseduce'
mysql -e "show databases" | grep piseduce
if [ $? -eq 1 ]; then
    # Variables
    MY_IP=$(hostname -I)
    DB_ROOT_PWD="rootDB"
    DB_USER_PWD="userDB"
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
    echo '# Configure the PiSeduce resource manager'
    sed -i "s/DBPASSWORD/$DB_USER_PWD/" /root/seduce_pp/seducepp.conf
    sed -i "s/PIMASTERIP/$MY_IP/" /tftpboot/rpiboot_uboot/cmdline.txt
    sed -i "s/PIMASTERIP/$MY_IP/" /root/seduce_pp/main.json
    # Compute the first node IP
    # Get the last digit of the IP
    # To RTFC: https://tldp.org/LDP/abs/html/string-manipulation.html
    last=$(echo ${MY_IP##*\.})
    next=$(( ($last + 10) / 10 * 10 + 1 ))
    first_ip="${MY_IP%$last*}$next"
    sed -i "s/FIRSTNODEIP/$first_ip/" /root/seduce_pp/main.json
    # Start the pifrontend
    /bin/systemctl restart pitasks
    /bin/systemctl restart pifrontend
fi
## End of PiSeduce Configuration ##

