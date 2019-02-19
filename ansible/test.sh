#!/bin/bash
set -eux

vl down
time vl up
vl ansible_inventory > inventory
ansible-playbook playbook.yml -i inventory -e dev_mode=1
vl down
rm inventory
