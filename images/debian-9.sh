#!/bin/bash

UPSTREAM_IMAGE_DIR=~/.local/share/libvirt/images/upstream
mkdir -p ${UPSTREAM_IMAGE_DIR}

curl -L -o ${UPSTREAM_IMAGE_DIR}/debian-9.qcow2 https://cdimage.debian.org/cdimage/openstack/current-9/debian-9-openstack-amd64.qcow2
virt-sysprep -a ${UPSTREAM_IMAGE_DIR}/debian-9.qcow2 --network --install qemu-guest-agent
