#!/bin/bash
set -eux

vl down
vl up
vl ansible_inventory > inventory
ansible-playbook playbook.yml -i inventory
vl down
