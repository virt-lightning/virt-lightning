# 🗲 a CLI to start local Cloud image on libvirt!🗲


[![Build Status](https://travis-ci.org/virt-lightning/virt-lightning.svg?branch=master)](https://travis-ci.org/virt-lightning/virt-lightning)
[![PyPI version](https://badge.fury.io/py/virt-lightning.svg)](https://badge.fury.io/py/virt-lightning)

![Logo](https://github.com/virt-lightning/virt-lightning/raw/master/logo/logo_no_text.png)

Virt-Lightning can quickly deploy a bunch of new VM. It
also prepares the Ansible inventory file!

This is handy to quickly validate a new Ansible playbook, or a role on a large number of environments.

## example: test an Ansible command on a new env in ONE minute ⚡

In a nutshell:

```shell
echo "- distro: centos-7" > virt-lightning.yaml
vl up
vl ansible_inventory
ansible all -m ping -i inventory
```

In the video below, we:

1. use the list of distribution to generate a virt-lightning.yaml file.
2. we then create a environment based on this file
3. once the environment is ready, we generate an Ansible inventory file
4. and we use it to call Ansible's ping module on all the host.

[![demo](https://asciinema.org/a/230671.svg)](https://asciinema.org/a/230671?autoplay=1)

## Pre-requirements



### Debian

First you need to install libvirt and guestfs:
```shell
sudo apt install -f libvirt-daemon libvirt-daemon-system python3 python3-libvirt python3-pip python3-urwid
sudo systemctl start --now libvirtd
```

The second step is to grant to your user the ability to use libvirt:
```shell
sudo usermod -a -G kvm,libvirt,libvirt-qemu $USER
```


### Fedora-29 and after

First you need to install libvirt and guestfs:
```shell
sudo dnf install -f libselinux-python libvirt libvirt-daemon python3 python3-libvirt python3-pip python3-urwid
sudo systemctl start --now libvirtd
```

The second step is to grant to your user the ability to use libvirt:
```shell
sudo usermod -a -G qemu,libvirt $USER
```


### Ubuntu-18.04

First you need to install libvirt and guestfs:
```shell
sudo apt install -f libvirt-bin libvirt-daemon python3 python3-libvirt python3-pip python3-urwid
sudo systemctl start --now libvirtd
```

The second step is to grant to your user the ability to use libvirt:
```shell
sudo usermod -a -G kvm,libvirt $USER
```


### Ubuntu-18.10 and after

First you need to install libvirt and guestfs:
```shell
sudo apt install -f libvirt-daemon libvirt-daemon-system python3 python3-libvirt python3-pip python3-urwid
sudo systemctl start --now libvirtd
```

The second step is to grant to your user the ability to use libvirt:
```shell
sudo usermod -a -G kvm,libvirt $USER
```

### RHEL-8

First you need to install libvirt and guestfs:
```shell
sudo apt install -f python3-libvirt libvirt qemu-kvm libvirt-daemon-kvm genisoimage
sudo systemctl start --now libvirtd
```

The second step is to grant to your user the ability to use libvirt:
```shell
sudo usermod -a -G libvirt $USER
```

### Void Linux

First you need to install libvirt and guestfs:
```shell
sudo xbps-install -Rs libvirt libvirt-python3 qemu python3-pip cdrtools dbus
sudo ln -s /etc/sv/dbus /var/service
sudo ln -s /etc/sv/libvirtd /var/service
sudo ln -s /etc/sv/virtlockd /var/service
sudo ln -s /etc/sv/virtlogd /var/service
```

The second step is to grant to your user the ability to use libvirt:
```shell
sudo usermod -a -G kvm,libvirt $USER
```

## Installation

```shell
pip3 install --user virt-lightning
```

If you use Ubuntu, you will need the `--no-deps` argument (See: https://github.com/pypa/pip/issues/4222).

`virt-lightning` will be installed in ~/.local/bin/. Add it in your `$PATH` if
it's not already the case. For instance if you use:

```shell
echo "export PATH=$PATH:~/.local/bin/" >> ~/.bashrc
source ~/.bashrc
```

# Fetch some images

Before you start your first VM, you need to fetch the images. To do so,
you just use the `vm fetch` command:

```shell
$ vl fetch fedora-32
```

## Build your images

If you prefer to build your own images,

```shell
$ git clone https://github.com/virt-lightning/virt-lightning
$ cd virt-lightning/images
$ ./image centos-7 build
$ ./image debian-9 build
(…)
```

Ubuntu requires the use *sudo* to build or prepare images.

You can also use your own images as soon as they embed cloud-init, just copy them in the QCOW2
format in /var/lib/virt-lightning/pool/upstream/. It's also a good idea to include qemu-guest-agent,
virt-lightning uses it to set the root password and it offers some other benefits.

# Actions

`vl` is an alias for `virt-lightning`, you can us both. In the rest of the document
we use the shortest version.

## **vl distro_list**

List the distro images that can be used. Its output is compatible with `vl up`. You can initialize a new configuration with: `vl distro > virt-lightning.yaml`.

## **vl up**

`virt-lightning` will read the `virt-lightning.yaml` file from the current directory and prepare the associated VM.

## **vl down**

Destroy all the VM managed by Virt-Lightning.

## **vl start**

Start a specific VM, without reading the `virt-lightning.yaml` file.

## **vl stop**

Stop just one VM.

## **vl status**

List the VM, their IP and if they are reachable.

## **vl ansible_inventory**

Export an inventory in the Ansible format.

## **vl ssh**

Show up a menu to select a host and open a ssh connection.

[![vl ssh](https://asciinema.org/a/230675.svg)](https://asciinema.org/a/230675?autoplay=1)

## **vl console**

Like `vl ssh` but with the serial console of the VM.

[![vl ssh](https://asciinema.org/a/230677.svg)](https://asciinema.org/a/230677?autoplay=1)


## **vl viewer**

Like `vl console` but with the SPICE console of the VM. Requires `virt-viewer`.

## **vl fetch**

Fetch a VM image. [You can find here a list of the available images](https://virt-lightning.org/images/).

# Configuration

## Global configuration

If `~/.config/virt-lightning/config.ini` exists, Virt-Lightning will read
its configuration there.

```ini
[main]
network_name = virt-lightning
root_password = root
storage_pool = virt-lightning
network_auto_clean_up = True
```

**network_name**: if you want to use an alternative libvirt network

**root_password**: the root password

**storage_pool**: if you want to use an alternative libvirt storage pool

**network_auto_clean_up**: if you want to automatically remove a network when running `virt-lightning down`

## VM configuration keys

A VM can be tunned at two different places with the following keys:

- `distro`: the name of the base distro image to use, it's the only mandatory parameter.
- `name`: the VM name
- `memory`: the amount of memory to dedicate to the VM
- `root_disk_size`: the size of the root disk in GB
- `vcpus`: the number of vcpu to dedicate to the VM
- `root_password`: the root password in clear text
- `groups`: this list of groups will be used if you generate an Ansible inventory.
- `networks`: a list of network to attach to the VM. The default is: one virtio interface attached to `virt-lightning` network.
    - `network`: the name of the network. Default is the key `network_name` from the configuration (`virt-lightning` by default)
    - `ipv4`: a static IPv4. Default is a dynamic IPv4 address.
    - `nic_model`: the libvirt driver to use. Default is `virtio`


### Example: a `virt-lightning.yaml` file:

```yaml
- name: esxi-vcenter
  distro: esxi-6.7
  memory: 12000
  root_disk_size: 30
  vcpus: 2
  root_password: '!234AaAa56'
  groups: ['all_esxi']
- name: esxi1
  distro: esxi-6.7
  memory: 4096
  vcpus: 1
  root_password: '!234AaAa56'
  groups: ['all_esxi', 'esxi_lab']
- name: esxi2
  distro: esxi-6.7
  memory: 4096
  vcpus: 1
  root_password: '!234AaAa56'
  groups: ['all_esxi', 'esxi_lab']
- name: centos-7
  distro: centos-7
  networks:
    - network: default
      ipv4: 192.168.122.50
  bootcmd:
    - yum update -y
```

### You can also associate some parameters to the distro image itself

```shell
cat /var/lib/virt-lightning/pool/upstream/esxi-6.7.yaml
username: root
python_interpreter: /bin/python
memory: 4096
networks:
  - network: virt-lightning
    nic_model: virtio
  - network: default
    nic_model: e1000
```
