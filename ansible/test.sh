#!/bin/bash
set -eux

vl down
time vl up
vl ansible_inventory > inventory
ansible-galaxy install -r requirements.yml -p roles/
ansible-playbook playbook.yml -i inventory -e dev_mode=1
vl down
rm inventory
