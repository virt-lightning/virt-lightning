#!/bin/sh

scp etc/caddy/conf.d/virt-lightning.org.conf virt-lightning.org:/etc/caddy/conf.d/virt-lightning.org.conf
scp www/images/index.md root@virt-lightning.org:/var/www/virt-lightning.org/images
ssh virt-lightning.org sudo systemctl restart caddy
