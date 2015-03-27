# -*- mode: ruby -*-
# vi: set ft=ruby :
VAGRANTFILE_API_VERSION = "2"

box = 'trusty64'
box_url = 'https://cloud-images.ubuntu.com/vagrant/trusty/current/trusty-server-cloudimg-amd64-vagrant-disk1.box'
hostname = 'fafserver.dev'

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  config.vm.box = box
  config.vm.box_url = box_url

  config.vm.provider "virtualbox" do |v|
    v.memory = 2048
  end

  config.vm.synced_folder ".", "/vagrant"

  # -- Networking ------------------------------------------

  config.vm.hostname = hostname

  # MySql
  # config.vm.network :forwarded_port, guest: 3306, host: 3306

  # -- Provisioning ----------------------------------------
  provision_dir = "vagrant/provision"

  vm = config.vm
  vm.provision :shell, path: "#{provision_dir}/vagrant_provision"
  vm.provision :shell, path: "#{provision_dir}/python_provision"
  vm.provision :shell, path: "#{provision_dir}/mysql_provision"
end

