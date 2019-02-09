#!/bin/bash

UPSTREAM_IMAGE_DIR=~/.local/share/libvirt/images/upstream
mkdir -p ${UPSTREAM_IMAGE_DIR}

#curl -L -o ${UPSTREAM_IMAGE_DIR}/fedora-29.qcow2 https://download.fedoraproject.org/pub/fedora/linux/releases/29/Cloud/x86_64/images/Fedora-Cloud-Base-29-1.2.x86_64.qcow2
network-scripts because of https://bugs.launchpad.net/cloud-init/+bug/1799301
virt-sysprep -a ${UPSTREAM_IMAGE_DIR}/fedora-29.qcow2 --network --update --install qemu-guest-agent,network-scripts,python --run-command 'systemctl enable qemu-guest-agent' --selinux-relabel
