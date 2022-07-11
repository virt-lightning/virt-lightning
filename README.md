# 🗲 spawn Cloud instances on libvirt!🗲


[![Build Status](https://travis-ci.org/virt-lightning/virt-lightning.svg?branch=master)](https://travis-ci.org/virt-lightning/virt-lightning)
[![PyPI version](https://badge.fury.io/py/virt-lightning.svg)](https://badge.fury.io/py/virt-lightning)
[![Documentation](https://shields.io/static/v1?message=Documentation&color=blue)](https://virt-lightning.org/)

![Logo](https://github.com/virt-lightning/virt-lightning/raw/master/logo/logo_no_text.png)

You want to spawn local VM quickly.. Like... really quickly. You want them to be as generical as possible. Actually you would like to reuse some existing cloud images!

This is the right tool for you.

Virt-Lightning exposes a CLI inspired by the Cloud and Vagrant.
It can also prepare the Ansible inventory file.

This is handy to quickly validate a new Ansible playbook, or a role on a large number of environments.

### example: less than 30 seconds to spawn an instance ⚡

In a nutshell:

```shell
echo "- distro: centos-7" > virt-lightning.yaml
vl up
vl ansible_inventory > inventory
ansible all -m ping -i inventory
```

### example: or 75 seconds for 10 nodes lab ⚡

During this recording, we:

1. use the list of distribution to generate a virt-lightning.yaml file.
2. we then create a environment based on this file
3. once the environment is ready, we generate an Ansible inventory file
4. and we use it to call Ansible's ping module on all the host.

[![demo](https://asciinema.org/a/230671.svg)](https://asciinema.org/a/230671?autoplay=1)

## Pre-requirements

- Python 3.8 or greater.
- The Python3 binding for libvirt, the package is probably called `python3-libvirt`.
- You make also want to install `python3-urwid` if you want to get the fancy list of VM. This dependency is optional.
- Libvirt must be running, most of the time you just need to run: `sudo systemctl start --now libvirtd`
- Finally, be sure your user can access the system libvirt daemon, e.g with: `virsh -c qemu:///system`

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
you just use the `vl fetch` command:

```shell
$ vl fetch fedora-32
```

# Actions

`vl` is an alias for `virt-lightning`, you can us both. In the rest of the document
we use the shortest version.

## **vl distro_list**

List the distro images that can be used. Its output is compatible with `vl up`. You can initialize a new configuration with: `vl distro_list > virt-lightning.yaml`.

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

Fetch a VM image. [You can find here a list of the available images](https://virt-lightning.org/images/). You can also update the custom configuration to add a private image hub.

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
ssh_key_file = ~/.ssh/id_rsa.pub
```

**network_name**: if you want to use an alternative libvirt network

**root_password**: the root password

**storage_pool**: if you want to use an alternative libvirt storage pool

**network_auto_clean_up**: if you want to automatically remove a network when running `virt-lightning down`

**ssh_key_file**: if you want to use an alternative public key

**private_hub**: if you need to set additional url from where images should be retrieved, update the configuration file `~/.config/virt-lightning/config.ini` adding the following
```
[main]
private_hub=url1,url2
```

## VM configuration keys

A VM can be tuned at two different places with the following keys:

- `distro`: the name of the base distro image to use, it's the only mandatory parameter.
- `name`: the VM name
- `memory`: the amount of memory to dedicate to the VM
- `vcpus`: the number of vcpu to dedicate to the VM
- `root_password`: the root password in clear text
- `ssh_key_file`: the path of the public key for connecting to the VM
- `groups`: this list of groups will be used if you generate an Ansible inventory.
- `disks`: a list of disks to create and attach to the VM. The first one is used as the root disk. Default to `[{"size": 15}]`
    - `size` the size of the disk in GB. Default is `1`.
- `networks`: a list of network to attach to the VM. The default is: one virtio interface attached to `virt-lightning` network.
    - `network`: the name of the libvirt network. Default is the key `network_name` from the configuration (`virt-lightning` by default). The key cannot be used with `bridge`.
    - `ipv4`: a static IPv4. Default is a dynamic IPv4 address.
    - `nic_model`: the libvirt driver to use. Default is `virtio`
    - `mac`: an optional static MAC address, e.g: '52:54:00:71:b1:b6'
    - `bridge`: optional, the name of a bridge to connect too. This key replace the `network` key.
    - `virtualport_type`: The type of the virtualport, currently, this is can be used with `bridge`.

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

### Example: connect to an OpenvSwitch bridge

```yaml
- name: controller
  distro: fedora-35
  - bridge: my-ovs-bridge-name
    virtualport_type: openvswitch
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
