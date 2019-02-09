# 🗲 Ride the Lightning!🗲

Virt-Lightning helps to quickly deployment a bunch of test VM. It
can also prepare the Ansible inventory file!

This is really handy to quickly validate a new playbook or a role on a large number of environments.

## Example ⚡

```shell
$ echo "- distro: centos-7" > virt-lightning.yaml
$ vl up
$ vl ansible_inventory
$ ansible all -m ping -i inventory
```
