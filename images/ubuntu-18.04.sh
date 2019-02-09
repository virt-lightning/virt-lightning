#!/bin/bash

UPSTREAM_IMAGE_DIR=~/.local/share/libvirt/images/upstream
mkdir -p ${UPSTREAM_IMAGE_DIR}

curl -L -o ${UPSTREAM_IMAGE_DIR}/ubuntu-18.04.qcow2 https://cloud-images.ubuntu.com/bionic/current/bionic-server-cloudimg-amd64.img
update-grub because of https://bugs.launchpad.net/cloud-images/+bug/1726476
virt-sysprep -a ${UPSTREAM_IMAGE_DIR}/ubuntu-18.04.qcow2 --network --install qemu-guest-agent,python --run-command update-grub
