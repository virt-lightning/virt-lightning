#!/usr/bin/env python3

import libvirt
import logging
import os
import pathlib
import string
import subprocess
import tempfile
import uuid
import warnings
import yaml

import xml.etree.ElementTree as ET


def libvirt_callback(userdata, err):
    pass


libvirt.registerErrorHandler(f=libvirt_callback, ctx=None)


DISK_XML = """
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source />
      <target bus='virtio'/>
    </disk>
"""

DOMAIN_XML = """
<domain type='kvm'>
  <name></name>
  <memory unit='KiB'>786432</memory>
  <currentMemory unit='KiB'>786432</currentMemory>
  <vcpu placement='static'>1</vcpu>
  <os>
    <type arch='x86_64' machine='pc-i440fx-3.0'>hvm</type>
    <boot dev='hd'/>
  </os>
  <features>
    <acpi/>
    <apic/>
    <vmport state='off'/>
  </features>
  <cpu mode='host-model' check='partial'>
    <model fallback='allow'/>
  </cpu>uu
  <clock offset='utc'>
    <timer name='rtc' tickpolicy='catchup'/>
    <timer name='pit' tickpolicy='delay'/>
    <timer name='hpet' present='no'/>
  </clock>
  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>destroy</on_crash>
  <pm>
    <suspend-to-mem enabled='no'/>
    <suspend-to-disk enabled='no'/>
  </pm>
  <devices>
    <emulator>/usr/bin/qemu-kvm</emulator>
    <controller type='usb' index='0' model='ich9-ehci1'>
      <address type='pci'/>
    </controller>
    <controller type='usb' index='0' model='ich9-uhci1'>
      <master startport='0'/>
      <address type='pci'/>
    </controller>
    <controller type='usb' index='0' model='ich9-uhci2'>
      <master startport='2'/>
      <address type='pci'/>
    </controller>
    <controller type='usb' index='0' model='ich9-uhci3'>
      <master startport='4'/>
      <address type='pci'/>
    </controller>
    <controller type='pci' index='0' model='pci-root'/>
    <controller type='ide' index='0'>
      <address type='pci'/>
    </controller>
    <controller type='virtio-serial' index='0'>
      <address type='pci'/>
    </controller>
    <serial type='pty'>
      <target type='isa-serial' port='0'>
        <model name='isa-serial'/>
      </target>
    </serial>
    <console type='pty'>
      <target type='serial' port='0'/>
    </console>
    <channel type='unix'>
      <target type='virtio' name='org.qemu.guest_agent.0'/>
      <address type='virtio-serial' controller='0' bus='0' port='1'/>
    </channel>
    <channel type='spicevmc'>
      <target type='virtio' name='com.redhat.spice.0'/>
      <address type='virtio-serial' controller='0' bus='0' port='2'/>
    </channel>
    <input type='mouse' bus='ps2'/>
    <input type='keyboard' bus='ps2'/>
    <graphics type='spice' autoport='yes'>
      <listen type='address'/>
      <image compression='off'/>
    </graphics>
    <sound model='ich6'>
      <address type='pci'/>
    </sound>
    <video>
      <model type='qxl' ram='65536' vram='65536' vgamem='16384' heads='1' primary='yes'/>
      <address type='pci'/>
    </video>
    <redirdev bus='usb' type='spicevmc'>
      <address type='usb' bus='0' port='1'/>
    </redirdev>
    <redirdev bus='usb' type='spicevmc'>
      <address type='usb' bus='0' port='2'/>
    </redirdev>
    <memballoon model='virtio'>
      <address type='pci'/>
    </memballoon>
    <rng model='virtio'>
      <backend model='random'>/dev/urandom</backend>
      <address type='pci'/>
    </rng>
  </devices>
</domain>
"""

BRIDGE_XML = """
<interface type='bridge'>
  <source bridge='virbr0'/>
  <model type='virtio'/>
  <address type='pci'/>
</interface>
"""


class LibvirtHypervisor:
    def __init__(self, configuration):
        conn = libvirt.open(
            configuration.get("libvirt_uri", "qemu:///session")
        )
        if conn is None:
            print("Failed to open connection to qemu:///session")
            exit(1)
        self.conn = conn
        self.configuration = configuration

    def create_domain(self):
        domain = LibvirtDomain.new(self.conn)
        root_password = self.configuration.get("root_password", "root")
        domain.cloud_init = {
            "resize_rootfs": True,
            "chpasswd": {"list": "root:%s" % root_password, "expire": False},
            "ssh_pwauth": True,
            "disable_root": 0,
            "mounts": [],
            "bootcmd": ["systemctl mask cloud-init"],
        }
        return domain

    def list_domains(self):
        for i in self.conn.listAllDomains():
            yield LibvirtDomain(i)


class LibvirtDomain:
    def __init__(self, dom):
        self.dom = dom
        self.cloud_init = None
        self._username = None
        self.wait_for = []
    def new(conn):
        root = ET.fromstring(DOMAIN_XML)
        e = root.findall("./name")[0]
        e.text = str(uuid.uuid4())[0:10]
        dom = conn.defineXML(ET.tostring(root).decode())
        return LibvirtDomain(dom)

    def ssh_key_file(self, ssh_key_file):
        self.ssh_key = open(os.path.expanduser(ssh_key_file), "r").read()
        self.cloud_init["ssh_authorized_keys"] = [self.ssh_key]
        if "users" in self.cloud_init:
            self.cloud_init["users"][0]["ssh_authorized_keys"] = [
                self.ssh_key
            ]

    def username(self, username=None):
        if username:
            self._username = username
            self.cloud_init["users"] = [
                {
                    "name": username,
                    "gecos": "virt-bootstrap user",
                    "sudo": "ALL=(ALL) NOPASSWD:ALL",
                    "ssh_authorized_keys": self.cloud_init.get(
                        "ssh_authorized_keys"
                    ),
                }
            ]

            meta = "<username name='%s' />" % username
            self.dom.setMetadata(
                libvirt.VIR_DOMAIN_METADATA_ELEMENT,
                meta,
                "vl",
                "username",
                libvirt.VIR_DOMAIN_AFFECT_CONFIG,
            )
        elif self._username:
            return self._username
        else:
            try:
                xml = self.dom.metadata(
                    libvirt.VIR_DOMAIN_METADATA_ELEMENT, "username"
                )
            except libvirt.libvirtError as e:
                if e.get_error_code() == libvirt.VIR_ERR_NO_DOMAIN_METADATA:
                    return None
                raise (e)
            elt = ET.fromstring(xml)
            return elt.attrib["name"]

    def name(self, name=None):
        if name:
            self.dom.rename(name, 0)
        return self.dom.name()

    def vcpus(self, value=None):
        if value:
            self.dom.setVcpusFlags(value, libvirt.VIR_DOMAIN_AFFECT_CONFIG)

    def memory(self, value=None):
        if value:
            self.dom.setMemoryFlags(
                value * 1024, libvirt.VIR_DOMAIN_AFFECT_CONFIG
            )

    def getNextBlckDevice(self):
        if not hasattr(self, "blockdev"):
            self.blockdev = list(string.ascii_lowercase)
            self.blockdev.reverse()
        return "vd%s" % self.blockdev.pop()

    def context(self, context=None):
        if context:
            meta = "<context name='%s' />" % context
            self.dom.setMetadata(
                libvirt.VIR_DOMAIN_METADATA_ELEMENT,
                meta,
                "vl",
                "context",
                libvirt.VIR_DOMAIN_AFFECT_CONFIG,
            )
        try:
            xml = self.dom.metadata(
                libvirt.VIR_DOMAIN_METADATA_ELEMENT, "context"
            )
        except libvirt.libvirtError as e:
            if e.get_error_code() == libvirt.VIR_ERR_NO_DOMAIN_METADATA:
                return None
            raise (e)
        elt = ET.fromstring(xml)
        return elt.attrib["name"]

    def attachDisk(self, path, device="disk", type="qcow2"):
        device_name = self.getNextBlckDevice()
        disk_root = ET.fromstring(DISK_XML)
        disk_root.attrib["device"] = device
        disk_root.findall("./driver")[0].attrib = {
            "name": "qemu",
            "type": type,
        }
        disk_root.findall("./source")[0].attrib = {"file": path}
        disk_root.findall("./target")[0].attrib = {"dev": device_name}
        xml = ET.tostring(disk_root).decode()
        self.dom.attachDeviceFlags(xml, libvirt.VIR_DOMAIN_AFFECT_CONFIG)
        return device_name

    def attachBridge(self, bridge):
        disk_root = ET.fromstring(BRIDGE_XML)
        disk_root.findall("./source")[0].attrib = {"bridge": bridge}
        xml = ET.tostring(disk_root).decode()
        self.dom.attachDeviceFlags(xml, libvirt.VIR_DOMAIN_AFFECT_CONFIG)

    def add_root_disk(self, distro, size=20):
        base_image_path = (
            "%s/.local/share/libvirt/images/upstream/%s.qcow2"
            % (pathlib.Path.home(), distro)
        )
        image_path = "%s/.local/share/libvirt/images/%s.qcow2" % (
            pathlib.Path.home(),
            self.name(),
        )
        proc = subprocess.Popen(
            [
                "qemu-img", "create",
                "-f", "qcow2",
                "-b", base_image_path,
                image_path,
                "%sG" % size,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        self.wait_for.append(proc)
        self.attachDisk(image_path)

    def add_swap_disk(self, size=1):
        swap_path = "%s/.local/share/libvirt/images/%s-swap.qcow2" % (
            pathlib.Path.home(),
            self.name(),
        )
        proc = subprocess.Popen(
            ["qemu-img", "create", "-f", "qcow2", swap_path, "%sG" % size],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        self.wait_for.append(proc)
        device_name = self.attachDisk(swap_path)
        self.cloud_init["mounts"].append(
            [device_name, "none", "swap", "sw", 0, 0]
        )
        self.cloud_init["bootcmd"].append("mkswap /dev/vdb")
        self.cloud_init["bootcmd"].append("swapon /dev/vdb")

    def dump(self):
        ET.dump(self.root)

    def prepare_meta_data(self):
        cidata_path = "%s/.local/share/libvirt/images/%s-cidata.iso" % (
            pathlib.Path.home(),
            self.name(),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(temp_dir + "/user-data", "w") as fd:
                fd.write("#cloud-config\n")
                fd.write(yaml.dump(self.cloud_init, Dumper=yaml.Dumper))
            with open(temp_dir + "/meta-data", "w") as fd:
                fd.write("dsmode: local\n")
                fd.write("instance-id: iid-%s\n" % self.name())
                fd.write("local-hostname: %s\n" % self.name())

            proc = subprocess.Popen(
                [
                    "genisoimage",
                    "-output",
                    cidata_path,
                    "-volid",
                    "cidata",
                    "-joliet",
                    "-r",
                    "user-data",
                    "meta-data",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=temp_dir,
            )
            proc.wait()
            self.wait_for.append(proc)
        self.attachDisk(cidata_path, device="cdrom", type="raw")

    def start(self):
        self.prepare_meta_data()
        for proc in self.wait_for:
            outs, errs = proc.communicate()
            if proc.returncode != 0:
                raise Exception("A command has failed: ", outs, errs)

        self.dom.create()

    def get_ipv4(self):
        try:
            ifaces = self.dom.interfaceAddresses(
                libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_AGENT, 0
            )
            for (_, val) in ifaces.items():
                for addr in val["addrs"]:
                    if addr["type"] != 0:  # 1 == IPv6
                        continue
                    if addr["addr"].startswith("127."):
                        continue
                    return addr["addr"]
        except (KeyError, TypeError):
            pass
        except libvirt.libvirtError:
            pass

    def set_user_password(self, user, password):
        return self.dom.setUserPassword(user, password)

    def clean_up(self):
        state, _ = self.dom.state()
        if state != libvirt.VIR_DOMAIN_SHUTOFF:
            self.dom.destroy()
        self.dom.undefine()

    def ssh_ping(self):
        ipv4 = self.get_ipv4()
        if not ipv4:
            return

        proc = subprocess.Popen(
            ["ssh", "-o", "StrictHostKeyChecking=no",
             "-o", "UserKnownHostsFile=/dev/null",
             "root@%s" % ipv4, "hostname"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        proc.wait()
        return True if proc.returncode == 0 else False
