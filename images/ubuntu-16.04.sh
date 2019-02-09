#!/bin/bash

UPSTREAM_IMAGE_DIR=~/.local/share/libvirt/images/upstream
mkdir -p ${UPSTREAM_IMAGE_DIR}

curl -L -o ${UPSTREAM_IMAGE_DIR}/ubuntu-16.04.qcow2 https://cloud-images.ubuntu.com/xenial/current/xenial-server-cloudimg-amd64-disk1.img
virt-sysprep -a ${UPSTREAM_IMAGE_DIR}/ubuntu-16.04.qcow2 --network --install qemu-guest-agent,python
