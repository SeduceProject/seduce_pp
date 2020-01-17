## Installation de PiSeduce dans une VM
* Linux Ubuntu Server 18.04.3 amd64

### Installation des paquets
```
sudo apt-key adv --recv-keys --keyserver hkp://keyserver.ubuntu.com:80 0xF1656F24C74CD1D8
sudo add-apt-repository "deb [arch=amd64,arm64,ppc64el] http://mariadb.mirror.liquidtelecom.com/repo/10.4/ubuntu $(lsb_release -cs) main"
sudo apt update

sudo apt install dnsmasq mariadb-client mariadb-server nfs-kernel-server python3-mysqldb python3-pip redis-server snmp
```

### SSH configuration
* Create the SSH key: `ssh-keygen`

### NFS server
* Create the shared directory
```
sudo mkdir -p /nfs/raspi1
sudo chown nobody:nogroup /nfs/
sudo chmod -R 777 /nfs/
```
* Upload the raspberry boot system to the shared directory from an existing server
```
rsync -av /nfs/raspi1/ pipi@192.168.122.236:/nfs/
```
* Add the SSH key of the nfs server to the rasberry environment
  * Edit /nfs/raspi1/root/.ssh/authorized_keys
* Append to /etc/exports: `/nfs *(rw,sync,no_subtree_check,no_root_squash)`
* Export the directory
```
sudo exportfs -a
sudo systemctl restart nfs-kernel-server
```

### DHCP Server on the hypervisor
* Edit /etc/dnsmasq.conf
```
listen-address=192.168.1.25

dhcp-range=192.168.1.0,static,255.255.255.0
dhcp-option=23,64

dhcp-host=B8:27:EB:76:30:6B,raspi1,192.168.1.51
dhcp-host=B8:27:EB:1f:11:f3,raspi2,192.168.1.52
dhcp-host=B8:27:EB:20:85:b9,raspi3,192.168.1.53
dhcp-host=b8:27:eb:b9:70:4c,raspi4,192.168.1.54
dhcp-host=b8:27:eb:1a:30:c2,raspi5,192.168.1.55
dhcp-host=b8:27:eb:e8:62:9c,raspi6,192.168.1.56
dhcp-host=b8:27:eb:bf:44:b1,raspi7,192.168.1.57
dhcp-host=b8:27:eb:ff:05:a5,raspi8,192.168.1.58
dhcp-host=b8:27:eb:a8:f8:3c,raspi9,192.168.1.59
dhcp-host=b8:27:eb:8f:a6:a1,raspi10,192.168.1.60
dhcp-host=b8:27:eb:7c:64:be,raspi11,192.168.1.61
dhcp-host=b8:27:eb:60:32:5b,raspi12,192.168.1.62
dhcp-host=b8:27:eb:5c:fc:3a,raspi13,192.168.1.63
dhcp-host=b8:27:eb:1c:5d:6c,raspi14,192.168.1.64
dhcp-host=b8:27:eb:95:d2:ae,raspi15,192.168.1.65
dhcp-host=b8:27:eb:ae:26:43,raspi16,192.168.1.66
dhcp-host=b8:27:eb:41:d6:5c,raspi17,192.168.1.67
dhcp-host=b8:27:eb:5a:94:f5,raspi18,192.168.1.68
dhcp-host=b8:27:eb:75:9e:2c,raspi19,192.168.1.69
dhcp-host=b8:27:eb:7a:80:80,raspi20,192.168.1.70
dhcp-host=b8:27:eb:96:c4:98,raspi21,192.168.1.71
dhcp-host=b8:27:eb:1c:4a:a6,raspi22,192.168.1.72
dhcp-host=b8:27:eb:d1:93:93,raspi23,192.168.1.73
dhcp-host=b8:27:eb:10:86:c5,raspi24,192.168.1.74

dhcp-ignore=tag:!known
interface=enp94s0f0
bind-interfaces

log-dhcp
dhcp-boot=/bootcode.bin,192.168.122.236,192.168.122.236
```
* Restart the service: `service dnsmasq restart`

### tftp server from dnsmasq
* Edit /etc/dnsmasq.conf
```
listen-address=192.168.122.236
interface=ens3
bind-interfaces
log-dhcp
enable-tftp
tftp-root=/tftpboot
pxe-service=0,"Raspberry Pi Boot"
tftp-no-blocksize
```
* Restart the service: `sudo service dnsmasq restart`

### Python requirements
pip3 install -r requirements.txt
pip3 install supervisor celery[redis]

### DB configuration
mysql -u root -p
```
CREATE DATABASE piseduce;
CREATE USER 'pipi'@'localhost' IDENTIFIED BY 'totopwd';
GRANT USAGE ON *.* TO 'pipi'@localhost IDENTIFIED BY 'totopwd';
GRANT USAGE ON *.* TO 'pipi'@'%' IDENTIFIED BY 'totopwd';
GRANT ALL PRIVILEGES ON piseduce.* TO 'pipi'@'localhost';
```

### Redis configuration
* Edit /etc/redis/redis.conf and set the supervised field to `supervised systemd`
* Restart redis: `sudo systemctl restart redis`

### seduce_pp configuration
* Create the configuration file seducepp.conf
```
mkdir -p  seduce_pp/conf/seducepp
touch seduce_pp/conf/seducepp/seducepp.conf
```
* Edit the file seducepp.conf
```
[frontend]
listen = 0.0.0.0
port = 8081
public_address = pi.seduce.fr

[api]
listen = 0.0.0.0
port = 5000
public_address = api.seduce.fr

[mail]
smtp_address = smtp.gmail.com
smtp_port = 587
account = toto@gmail.com
password = totopwd

[admin]
user = toto@gmail.com
password = totopwd
firstname = Super
lastname = Admin
url_picture = /static/assets/faces/superman.png

[influx]
address = 127.0.0.1
port = 8086
user = root
password = root
db = pidiou

[bot]
token = tototoken

[redis]
address = 127.0.0.1
port = 6379

[db]
connection_url=mysql://pipi:piseduce@localhost/piseduce

[captcha]
site_key=totokey
secret_key=totokey
```
* Configure the controller to deploy environments on raspberry
  * Edit lib/config/cluster_config.py
  * Set the controller IP with your IP: `"ip": "192.168.122.236"`
  * Set the controller SSH key
  * Set the controller SSH user
* Add the SSH key of the raspberry from the NFS filesystem to your 
  * sudo cat /nfs/raspi1/root/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys

### Process Control System: supervisord
* Create the configuration file in /etc/supervisord.conf
```
[unix_http_server]
file=/tmp/supervisor.sock   ; the path to the socket file

[supervisord]
logfile=/tmp/supervisord.log ; main log file; default $CWD/supervisord.log
logfile_maxbytes=50MB        ; max main logfile bytes b4 rotation; default 50MB
logfile_backups=10           ; # of main logfile backups; 0 means none, default 10
loglevel=info                ; log level; default info; others: debug,warn,trace
pidfile=/tmp/supervisord.pid ; supervisord pidfile; default supervisord.pid
nodaemon=false               ; start in foreground if true; default false
minfds=1024                  ; min. avail startup file descriptors; default 1024
minprocs=200                 ; min. avail process descriptors;default 200

[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface
[supervisorctl]
serverurl=unix:///tmp/supervisor.sock ; use a unix:// URL  for a unix socket

[program:frontend]
user=pipi
command=python3 app.py
directory=/home/pipi/seduce_pp
stdout_logfile=/tmp/frontend.log
stderr_logfile=/tmp/frontend_err.log

[program:tasks]
user=pipi
command=python3 celery_tasks.py
directory=/home/pipi/seduce_pp
stdout_logfile=/tmp/tasks.log
stderr_logfile=/tmp/tasks_err.log
```
* Start the daemon: `supervisord`
* Control servives supervisorctl:
  * `supervisorctl status`
  * `supervisorctl update`
  * `supervisorctl restart tasks`

* Start supervisord at startup
```
sudo vim /etc/rc.local
sudo -i -u pipi supervisord
sudo chmod +x /etc/rc.local
```

### Create a pi user
* Connect to the web interface (localhost:9010, check the last line in app.py)
* Confirm the user from the command: 
```
mysql -upipi -p piseduce -e "UPDATE user SET email_confirmed=1, state='confirmed' WHERE email='remy.pottier@imt-atlantique.fr'"
```

### Create the NFS directory to boot Raspberry Pi (FAILED)
* Deploy a Raspberry Pi
* Create the filesystem archive
```
apt update && apt -y dist-upgrade && apt -y autoremove && apt autoclean && apt install rsync
dphys-swapfile swapoff
dphys-swapfile uninstall
update-rc.d dphys-swapfile remove
mkdir -p /nfs/client1
apt-get install -y rsync
rsync -xa --progress --exclude /nfs / /nfs/client1
cd /nfs/client1
mount --bind /dev dev
mount --bind /sys sys
mount --bind /proc proc
chroot .
rm /etc/ssh/ssh_host_*
exit
umount dev
umount sys
umount proc
rm /nfs/client1/var/swap
tar -cpf /nfs.tar /nfs
```
* Uncompress tar in the NFS server with `tar --same-owner -xvf nfs.tar`
* Try to fix the NFS boot by changing permissions
```
chmod 755 -R /nfs/raspi1/
cd /nfs/raspi1
chmod 700 root/
cd .ssh
chmod 644 *
chmod 600 ssh_host_dsa_key ssh_host_ecdsa_key ssh_host_ed25519_key ssh_host_rsa_key
chmod ... /etc/ssh
```

