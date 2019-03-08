# 🗲 Ride the Lightning!🗲

![Logo](logo/logo_no_text.png)

Virt-Lightning can quickly deploy a bunch of new VM. It
also prepares the Ansible inventory file!

This is really handy to quickly validate a new Ansible playbook, or a role on a large number of environments.

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



<details><summary>Debian</summary>
<p>

First you need to install libvirt and guestfs:
```shell
sudo apt install -f libguestfs-tools libvirt-daemon libvirt-daemon-system python3 python3-libvirt python3-pip python3-urwid
sudo systemctl start --now libvirtd
```

The second step is to grant to your user the ability to use libvirt:
```shell
sudo usermod -a -G kvm,libvirt,libvirt-qemu $USER
```
</p>
</details>


<details><summary>Fedora-29</summary>
<p>

First you need to install libvirt and guestfs:
```shell
sudo apt install -f libguestfs-tools libselinux-python libvirt python3 python3-libvirt python3-pip python3-urwid
sudo systemctl start --now libvirtd
```

The second step is to grant to your user the ability to use libvirt:
```shell
sudo usermod -a -G qemu,libvirt $USER
```
</p>
</details>


<details><summary>Ubuntu-16.04</summary>
<p>

First you need to install libvirt and guestfs:
```shell
sudo apt install -f libguestfs-tools libvirt-bin libvirt-daemon python3 python3-libvirt python3-pip python3-urwid
sudo systemctl start --now libvirtd
```

The second step is to grant to your user the ability to use libvirt:
```shell
sudo usermod -a -G kvm,libvirtd $USER
```
</p>
</details>


<details><summary>Ubuntu-18.04</summary>
<p>

First you need to install libvirt and guestfs:
```shell
sudo apt install -f libguestfs-tools libvirt-bin libvirt-daemon python3 python3-libvirt python3-pip python3-urwid
sudo systemctl start --now libvirtd
```

The second step is to grant to your user the ability to use libvirt:
```shell
sudo usermod -a -G kvm,libvirt $USER
```
</p>
</details>


<details><summary>Ubuntu-18.10</summary>
<p>

First you need to install libvirt and guestfs:
```shell
sudo apt install -f libguestfs-tools libvirt-daemon libvirt-daemon-system python3 python3-libvirt python3-pip python3-urwid
sudo systemctl start --now libvirtd
```

The second step is to grant to your user the ability to use libvirt:
```shell
sudo usermod -a -G kvm,libvirt $USER
```
</p>
</details>



## Installation

```shell
pip3 install --user --no-deps git+https://github.com/virt-lightning/virt-lightning
```

The `--no-deps` argument is only required on Ubuntu (See: https://github.com/pypa/pip/issues/4222).

`virt-lightning` will be installed in ~/.local/bin/. Add it in your `$PATH` if
it's not already the case. For instance if you use:

```shell
echo "export PATH=$PATH:~/.local/bin/" >> ~/.bashrc
source ~/.bashrc
```

# Fetch some images

Before you start your first VM, you need to fetch the images. To do so,
you just need these scripts:
https://github.com/virt-lightning/virt-lightning/tree/master/images

```shell
$ git clone https://github.com/virt-lightning/virt-lightning
$ cd virt-lightning/images
$ ./image centos-7 build
$ ./image debian-9 build
(…)
```

Ubuntu requires use *sudo* to build or prepare images.

You can also use your own images as soon as they embed cloud-init, just copy them in the QCOW2
format in /var/lib/virt-lightning/pool/upstream/. It's also a good idea to include qemu-guest-agent,
virt-lightning uses it to set the root password and it offers some other benefits.

# Actions

`vl` is an alias for `virt-lightning`, you can us both. In the rest of the document
we use the shortest version.

- **vl distro_list**: List the distro images that can be used. Its output is compatible with `vl up`. You can initialize a new configuration with: `vl distro > virt-lightning.yaml`.
- **vl up**: `virt-lightning` will read the `virt-lightning.yaml` file from the current directory and prepare the associated VM.
- **vl down**: Destroy all the VM.
- **vl status**: List the VM, their IP and if they are reachable.
- **vl ansible_inventory**: Export an inventory in the Ansible format.
- **vl ssh**: Show up a menu to select a host and open a ssh connection [![vl ssh](https://asciinema.org/a/230675.svg)](https://asciinema.org/a/230675?autoplay=1)
- **vl console**: Like `vl ssh` but with the serial console of the VM [![vl ssh](https://asciinema.org/a/230677.svg)](https://asciinema.org/a/230677?autoplay=1)

### Configuration from file

You can create your own configuration file like this and save to config.ini

```
[main]
network_name = virt-lightning
root_password = root
storage_pool = virt-lightning
```