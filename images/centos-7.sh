#!/bin/bash

UPSTREAM_IMAGE_DIR=~/.local/share/libvirt/images/upstream
mkdir -p ${UPSTREAM_IMAGE_DIR}

curl -L -o ${UPSTREAM_IMAGE_DIR}/centos-7.qcow2 https://cloud.centos.org/centos/7/images/CentOS-7-x86_64-GenericCloud.qcow2
virt-sysprep -v -x -a ${UPSTREAM_IMAGE_DIR}/centos-7.qcow2 --network --update --selinux-relabel
