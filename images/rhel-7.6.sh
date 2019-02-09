#!/bin/bash

UPSTREAM_IMAGE_DIR=~/.local/share/libvirt/images/upstream
mkdir -p ${UPSTREAM_IMAGE_DIR}

curl -L -o ${UPSTREAM_IMAGE_DIR}/rhel-7.6.qcow2 http://download-node-02.eng.bos.redhat.com/released/RHEL-7/7.6/Server/x86_64/images/rhel-guest-image-7.6-210.x86_64.qcow2
