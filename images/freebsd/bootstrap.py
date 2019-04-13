#!/usr/bin/python3

import argparse
import subprocess
import urllib.request

manual_step = """
Now, FreeBSD will start in qemu. You will have to do a few manual steps:

    log in as root
      # mount_cd9660 /dev/cd0 /media
      # sh /media/prepare.sh

    The VM will stop by itself, just close the qemu window at the end.
      [tip: Use ctrl+alt+g to release focus from the qemu window]
"""

mapping = {
    '11.2': 'https://download.freebsd.org/ftp/releases/VM-IMAGES/11.2-RELEASE/amd64/Latest/FreeBSD-11.2-RELEASE-amd64.qcow2.xz',
    '12.0': 'http://ftp.freebsd.org/pub/FreeBSD/snapshots/VM-IMAGES/12.0-STABLE/amd64/Latest/FreeBSD-12.0-STABLE-amd64.qcow2.xz',
    '13.0': 'http://ftp.freebsd.org/pub/FreeBSD/snapshots/VM-IMAGES/13.0-CURRENT/amd64/Latest/FreeBSD-13.0-CURRENT-amd64.qcow2.xz'}


parser = argparse.ArgumentParser(description='Prepare FreeBSD Cloud image with cloud-init')
parser.add_argument(
        'version', type=str,
        help='FreeBSD version: %s' % list(mapping.keys()))
args = parser.parse_args()

print("* Preparing the ISO image")
subprocess.check_call(['genisoimage', '-output', 'prepare.iso', '-volid', 'prepare', '-joliet', '-r', 'prepare.sh'])
print("* Downloading")
urllib.request.urlretrieve(mapping[args.version], 'freebsd-{version}.qcow2.xz'.format(version=args.version))

print("* Extracting")
subprocess.check_call(['unxz', 'freebsd-{version}.qcow2.xz'.format(version=args.version)])

print(manual_step)
subprocess.check_call(['qemu-system-x86_64', '-drive', 'file=freebsd-{version}.qcow2'.format(version=args.version), '-cdrom', 'prepare.iso', '-net', 'nic,model=virtio', '-net', 'user', '-m', '1G'])

print('* Done! Your image is ready: freebsd-{version}.qcow2'.format(version=args.version))
print('Note: The FreeBSD images are 31GB large, do not '
      'create a VM with a small system disk image!')
