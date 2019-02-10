#!/usr/bin/env python3

import os
import pathlib
import re
import string
import subprocess
import tempfile
import uuid
import xml.etree.ElementTree as ET

import libvirt

import yaml


from .templates import BRIDGE_XML, DISK_XML, DOMAIN_XML


def libvirt_callback(userdata, err):
    pass


libvirt.registerErrorHandler(f=libvirt_callback, ctx=None)


class LibvirtHypervisor:
    def __init__(self, configuration, uri="qemu:///session"):
        conn = libvirt.open(configuration.get("libvirt_uri", uri))
        if conn is None:
            print("Failed to open connection to {uri}".format(uri=uri))
            exit(1)
        self.conn = conn
        self.configuration = configuration

    def create_domain(self):
        domain = LibvirtDomain.new(self.conn)
        domain.cloud_init = {
            "resize_rootfs": True,
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
        self.cloud_init = []
        self._username = None
        self.ssh_key = None
        self.wait_for = []

    def new(conn):
        root = ET.fromstring(DOMAIN_XML)
        e = root.findall("./name")[0]
        e.text = str(uuid.uuid4())[0:10]
        dom = conn.defineXML(ET.tostring(root).decode())
        return LibvirtDomain(dom)

    def root_password(self, root_password=None):
        if root_password:
            self.cloud_init["chpassd"] = {
                "list": "root:{root_password}".format(root_password=root_password),
                "expire": False,
            }
        chpassd = self.cloud_init.get("chpassd")
        if chpassd:
            return chpassd["list"].split(":")[1]

    def ssh_key_file(self, ssh_key_file):
        try:
            with open(os.path.expanduser(ssh_key_file), "r") as fd:
                self.ssh_key = fd.read()
        except IOError:
            print("Can not read {filename}".format(filename=ssh_key_file))

        if self.ssh_key and len(self.ssh_key) > 0:
            self.cloud_init["ssh_authorized_keys"] = [self.ssh_key]
            if "users" in self.cloud_init:
                self.cloud_init["users"][0]["ssh_authorized_keys"] = [self.ssh_key]

    def username(self, username=None):
        is_valid_username = re.match("[a-z_][a-z0-9_-]*$", username)

        if is_valid_username and len(username) <= 32:
            self._username = username
            self.cloud_init["users"] = [
                {
                    "name": username,
                    "gecos": "virt-bootstrap user",
                    "sudo": "ALL=(ALL) NOPASSWD:ALL",
                    "ssh_authorized_keys": self.cloud_init.get("ssh_authorized_keys"),
                }
            ]

            meta = "<username name='{username}' />".format(username=username)
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
                xml = self.dom.metadata(libvirt.VIR_DOMAIN_METADATA_ELEMENT, "username")
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
            self.dom.setMemoryFlags(value, libvirt.VIR_DOMAIN_AFFECT_CONFIG)

    def getNextBlckDevice(self):
        if not hasattr(self, "blockdev"):
            self.blockdev = list(string.ascii_lowercase)
            self.blockdev.reverse()
        return "vd{block}".format(block=self.blockdev.pop())

    def context(self, context=None):
        if context:
            meta = "<context name='{context}' />".format(context=context)
            self.dom.setMetadata(
                libvirt.VIR_DOMAIN_METADATA_ELEMENT,
                meta,
                "vl",
                "context",
                libvirt.VIR_DOMAIN_AFFECT_CONFIG,
            )
        try:
            xml = self.dom.metadata(libvirt.VIR_DOMAIN_METADATA_ELEMENT, "context")
        except libvirt.libvirtError as e:
            if e.get_error_code() == libvirt.VIR_ERR_NO_DOMAIN_METADATA:
                return None
            raise (e)
        elt = ET.fromstring(xml)
        return elt.attrib["name"]

    def attachDisk(self, path, device="disk", disk_type="qcow2"):
        device_name = self.getNextBlckDevice()
        disk_root = ET.fromstring(DISK_XML)
        disk_root.attrib["device"] = device
        disk_root.findall("./driver")[0].attrib = {"name": "qemu", "type": disk_type}
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
        base_image_path_template = (
            "{path}/.local/share/libvirt/" "images/upstream/{distro}.qcow2"
        )
        base_image_path = base_image_path_template.format(
            path=pathlib.Path.home(), distro=distro
        )
        image_path = "{path}/.local/share/libvirt/images/{name}.qcow2".format(
            path=pathlib.Path.home(), name=self.name()
        )
        proc = subprocess.Popen(
            [
                "qemu-img",
                "create",
                "-f",
                "qcow2",
                "-b",
                base_image_path,
                image_path,
                "{size}G".format(size=size),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.wait_for.append(proc)
        self.attachDisk(image_path)

    def add_swap_disk(self, size=1):
        swap_path = "{path}/.local/share/libvirt/images/{name}-swap.qcow2".format(
            path=pathlib.Path.home(), name=self.name()
        )
        proc = subprocess.Popen(
            [
                "qemu-img",
                "create",
                "-f",
                "qcow2",
                swap_path,
                "{size}G".format(size=size),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.wait_for.append(proc)
        device_name = self.attachDisk(swap_path)
        self.cloud_init["mounts"].append([device_name, "none", "swap", "sw", 0, 0])
        self.cloud_init["bootcmd"].append("mkswap /dev/vdb")
        self.cloud_init["bootcmd"].append("swapon /dev/vdb")

    def dump(self):
        ET.dump(self.root)

    def prepare_meta_data(self):
        cidata_path = "{path}/.local/share/libvirt/images/{name}-cidata.iso".format(
            path=pathlib.Path.home(), name=self.name()
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(temp_dir + "/user-data", "w") as fd:
                fd.write("#cloud-config\n")
                fd.write(yaml.dump(self.cloud_init, Dumper=yaml.Dumper))
            with open(temp_dir + "/meta-data", "w") as fd:
                fd.write("dsmode: local\n")
                fd.write("instance-id: iid-{name}\n".format(name=self.name()))
                fd.write("local-hostname: {name}\n".format(name=self.name()))

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
        self.attachDisk(cidata_path, device="cdrom", disk_type="raw")

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
            [
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                "root@{ipv4}".format(ipv4=ipv4),
                "hostname",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        proc.wait()
        return True if proc.returncode == 0 else False
