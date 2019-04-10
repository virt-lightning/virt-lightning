#!/bin/sh
export ASSUME_ALWAYS_YES=YES
cd /tmp
fetch --no-verify-peer https://github.com/goneri/cloud-init/archive/freebsd.tar.gz
tar xf freebsd.tar.gz
cd cloud-init-freebsd
mkdir -p /usr/local/etc/rc.d
./tools/build-on-freebsd

echo 'boot_multicons="YES"' >> /boot/loader.conf
echo 'boot_serial="YES"' >> /boot/loader.conf
echo 'comconsole_speed="115200"' >> /boot/loader.conf
echo 'console="comconsole,vidconsole"' >> /boot/loader.conf
echo '-P' >> /boot.config

echo 'sshd_enable="YES"' >> /etc/rc.conf
echo 'sendmail_enable="NONE"' >> /etc/rc.conf
echo 'autoboot_delay="1"' >> /boot/loader.conf
echo '' > /etc/resolv.conf
shutdown -p now
