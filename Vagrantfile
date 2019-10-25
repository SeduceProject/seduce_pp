Vagrant.configure("2") do |config|
 config.vm.box = "bento/ubuntu-18.04"

 config.vm.network "public_network"

 config.vm.network "forwarded_port", guest: 9000, host: 9000
 config.vm.network "forwarded_port", guest: 3306, host: 9006
 
 config.vm.provision "ansible_local" do |a|
   a.playbook = "setup.yml"
 end
end