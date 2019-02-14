# 🗲 Ride the Lightning!🗲

Virt-Lightning can quickly deployment a bunch of new VM. It
can also prepare the Ansible inventory file!

This is really handy to quickly validate a new playbook or a role on a large number of environments.

## Example ⚡

```shell
echo "- distro: centos-7" > virt-lightning.yaml
vl up
vl ansible_inventory
ansible all -m ping -i inventory
```

## Installation

### Fedora 29

First you need to install libvirt and guestfs:
```shell
sudo dnf install -y python3 libvirt libguestfs-tools python3-libvirt python3-virtualenv libvirt-devel
sudo systemctl start --now libvirtd
```

The second step is to grant to your user the ability to use libvirt:
```shell
sudo usermod -a -G qemu,libvirt $USER
sudo chmod g+x $HOME
```

Finally we can prepare a virtualenv:
```shell
python3 -m venv venv
source venv/bin/activate
pip install git+https://github.com/virt-lightning/virt-lightning
```

## Fetch some images

Before you start your first VM, you need to fetch the images. To do so,
you just need these scripts:
https://github.com/virt-lightning/virt-lightning/tree/master/images

```shell
git clone https://github.com/virt-lightning/virt-lightning
cd virt-lightning/images
./image centos-7 build
./image debian-9 build
(etc)
```

## Actions

`vl` is an alias for `virt-lightning`, you can us both. In the rest of the document
we use the shortest version.

### vl up

`virt-lightning` will read the `virt-lightning.yaml` file from the current directory and prepare the associated VM.

### vl down

Destroy the VM.

	Flash before my eyes
	Now it's time to die
	Burning in my brain
	I can feel the flame

### vl status

List the VM, their IP and if they are reachable.

### vl ansible_inventory

Export an inventory in the Ansible format.

### vl distro

List the distro images that can be used. Its output is compatible with `vl up`.
You can initialize a new configuration with: `vl distro > virt-lightning.yaml`.

### Performance profiling

```shell
time vl up
vl ansible_inventory > inventory
ansible all -m shell -a "systemd-analyze blame|head -n 5" -i inventory
```

### Configuration from file

You can create your own configuration file like this and save to config.ini

```
[main]
network = 192.168.122.0/24
gateway = 192.168.122.1/24
bridge = virbr0
root_password = root
storage_pool = default
```

After creation configuration you can use `vl` command with `--config` argument and provide location to your config file.

```shell
vl --config config.ini
```
