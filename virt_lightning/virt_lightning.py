#!/usr/bin/env python3

import ipaddress
import getpass
import logging
import os
import pathlib
import re
import string
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET

import libvirt

import json
import yaml

import asyncio

from virt_lightning.symbols import get_symbols

from .templates import (
    BRIDGE_XML,
    CLOUD_INIT_ENI,
    NETWORK_DHCP_ENTRY,
    DISK_XML,
    DOMAIN_XML,
    NETWORK_HOST_ENTRY,
    NETWORK_XML,
    STORAGE_POOL_XML,
    STORAGE_VOLUME_XML,
    USER_CREATE_STORAGE_POOL_DIR,
)

DEFAULT_STORAGE_DIR = "/var/lib/virt-lightning/pool"
QEMU_DIR = "/var/lib/libvirt/qemu/"
KVM_BINARIES = (
    "/usr/bin/qemu-system-x86_64",
    "/usr/bin/qemu-kvm",
    "/usr/bin/kvm",
    "/usr/libexec/qemu-kvm",
)

logger = logging.getLogger("virt_lightning")

symbols = get_symbols()


def run_cmd(cmd, cwd=None):
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd
    )
    outs, errs = proc.communicate()
    if proc.returncode != 0:
        raise Exception("A command has failed: ", outs, errs)


class LibvirtHypervisor:
    def __init__(self, conn):
        if conn is None:
            logger.error("Failed to open connection to libvirt")
            exit(1)

        self.conn = conn
        self._last_free_ipv4 = None
        self.storage_pool_obj = None
        self.network_obj = None
        self.gateway = None
        self.dns = None
        self.network = None

    @property
    def arch(self):
        caps = self.conn.getCapabilities()
        root = ET.fromstring(caps)
        return root.find("./host/cpu/arch").text

    @property
    def domain_type(self):
        caps = self.conn.getCapabilities()
        root = ET.fromstring(caps)
        available = [
            e.attrib["type"] for e in root.findall("./guest/arch/domain[@type]")
        ]
        if not available:
            raise Exception("No domain type available!")
        if "kvm" not in available:
            logger.warning("kvm mode not available!")
        # Sorted to get kvm before qemu, assume there is no other type
        return sorted(available)[0]

    def create_domain(self, name=None, distro=None):
        if not name:
            name = uuid.uuid4().hex[0:10]
        root = ET.fromstring(DOMAIN_XML)
        root.attrib["type"] = self.domain_type
        root.find("./name").text = name
        root.find("./vcpu").text = str(self.conn.getInfo()[2])
        root.find("./devices/emulator").text = str(self.kvm_binary)
        root.find("./os/type").attrib["arch"] = self.arch
        dom = self.conn.defineXML(ET.tostring(root).decode())
        domain = LibvirtDomain(dom)
        domain.distro = distro
        return domain

    def configure_domain(self, domain, user_config):
        config = {
            "groups": [],
            "memory": 768,
            "python_interpreter": "/usr/bin/python3",
            "root_password": "root",
            "username": getpass.getuser(),
            "vcpus": 1,
        }
        for k, v in self.get_distro_configuration(domain.distro).items():
            if v:
                config[k] = v
        for k, v in user_config.items():
            if v:
                config[k] = v
        domain.groups = config["groups"]
        domain.load_ssh_key_file(config["ssh_key_file"])
        domain.memory = config["memory"]
        domain.python_interpreter = config["python_interpreter"]
        domain.root_password = config["root_password"]
        domain.username = config["username"]
        domain.vcpus = config["vcpus"]

    def get_distro_configuration(self, distro):
        distro_configuration_file = pathlib.PosixPath(
            "{storage_dir}/upstream/{distro}.yaml".format(
                storage_dir=self.get_storage_dir(), distro=distro
            )
        )
        if not distro_configuration_file.exists():
            return {}
        return yaml.load(distro_configuration_file.open("r"), Loader=yaml.SafeLoader)

    def list_domains(self):
        for i in self.conn.listAllDomains():
            yield LibvirtDomain(i)

    def get_domain_by_name(self, name):
        try:
            dom = self.conn.lookupByName(name)
            return LibvirtDomain(dom)
        except libvirt.libvirtError as e:
            if e.get_error_code() == libvirt.VIR_ERR_NO_DOMAIN:
                return None
            else:
                raise

    def get_free_ipv4(self):
        used_ips = [self.gateway]
        for dom in self.list_domains():
            ipstr = dom.get_metadata("ipv4")
            if not ipstr:
                continue
            interface = ipaddress.ip_interface(ipstr)
            used_ips.append(interface)

        for ip in self.network:
            cidr_ip = "{ip}/24".format(ip=ip)
            interface = ipaddress.IPv4Interface(cidr_ip)
            if int(interface.ip.exploded.split(".")[3]) < 5:
                continue
            if self._last_free_ipv4 and self._last_free_ipv4 >= interface:
                continue
            if interface not in used_ips:
                self._last_free_ipv4 = interface
                return interface

    def get_storage_dir(self):
        xml = self.storage_pool_obj.XMLDesc(0)
        root = ET.fromstring(xml)
        disk_source = root.find("./target/path")
        return pathlib.PosixPath(disk_source.text)

    def create_disk(self, name, size=None, backing_on=None):
        if "/" in name:
            raise TypeError
        if not size:
            size = 20
        disk_path = pathlib.PosixPath(
            "{path}/{name}.qcow2".format(path=self.get_storage_dir(), name=name)
        )
        logger.debug("create_disk: %s (%dGB)", str(disk_path), size)
        root = ET.fromstring(STORAGE_VOLUME_XML)
        root.find("./name").text = disk_path.name
        root.find("./capacity").text = str(size)
        root.find("./target/path").text = str(disk_path)

        if backing_on:
            backing_file = pathlib.PosixPath(
                "{path}/upstream/{backing_on}.qcow2".format(
                    path=self.get_storage_dir(), backing_on=backing_on
                )
            )
            backing = ET.SubElement(root, "backingStore")
            ET.SubElement(backing, "path").text = str(backing_file)
            ET.SubElement(backing, "format").attrib = {"type": "qcow2"}

        xml = ET.tostring(root).decode()
        try:
            return self.storage_pool_obj.createXML(xml)
        except libvirt.libvirtError as e:
            if e.get_error_code() == libvirt.VIR_ERR_STORAGE_VOL_EXIST:
                logger.error(
                    (
                        "A volume image already exists and prevent the creation "
                        " of a new one. You can remove it with the following "
                        "command:\n"
                        "  sudo virsh vol-delete --pool "
                        "{pool_name} {vol_name}.qcow2"
                    ).format(pool_name=self.storage_pool_obj.name(), vol_name=name)
                )
                sys.exit(1)
            raise

    def prepare_cloud_init_openstack_iso(self, domain):
        with tempfile.TemporaryDirectory() as base_temp_dir:
            temp_dir = pathlib.Path(base_temp_dir)
            cd_dir = temp_dir / "cd_dir"
            cd_dir.mkdir()

            openstack_meta_data = {
                "availability_zone": "nova",
                "files": [],
                "hostname": domain.name,
                "launch_index": 0,
                "name": domain.name,
                "meta": {},
                "public_keys": {"default": domain.ssh_key},
                "uuid": domain.dom.UUIDString(),
            }
            openstack_network_data = {
                "links": [
                    {
                        "id": "interface0",
                        "type": "phy",
                        "ethernet_mac_address": domain.mac_addresses[0],
                    }
                ],
                "networks": [
                    {
                        "id": "private-ipv4",
                        "type": "ipv4",
                        "link": "interface0",
                        "ip_address": str(domain.ipv4.ip),
                        "netmask": str(self.network.netmask.exploded),
                        "routes": [
                            {
                                "network": "0.0.0.0",
                                "netmask": "0.0.0.0",
                                "gateway": str(self.gateway.ip),
                            }
                        ],
                        "network_id": "da5bb487-5193-4a65-a3df-4a0055a8c0d7",
                    }
                ],
                "services": [{"type": "dns", "address": str(self.dns.ip)}],
            }

            openstack_dir = cd_dir / "openstack" / "latest"
            openstack_dir.mkdir(parents=True)
            openstack_metadata_file = openstack_dir / "meta_data.json"
            with openstack_metadata_file.open("w") as fd:
                fd.write(json.dumps(openstack_meta_data))
            openstack_networkdata_file = openstack_dir / "network_data.json"
            with openstack_networkdata_file.open("w") as fd:
                fd.write(json.dumps(openstack_network_data))
            openstack_userdata_file = openstack_dir / "user_data"
            with openstack_userdata_file.open("w") as fd:
                fd.write("#cloud-config\n")
                fd.write(yaml.dump(domain.cloud_init, Dumper=yaml.Dumper))

            cidata_file = temp_dir / "{name}-cidata.iso".format(name=domain.name)
            run_cmd(
                [
                    "genisoimage",
                    "-output",
                    cidata_file.name,
                    "-volid",
                    "config-2",
                    "-joliet",
                    "-R",
                    str(cd_dir),
                ],
                cwd=str(temp_dir),
            )

            cdrom = self.create_disk(name=cidata_file.stem, size=1)
            with cidata_file.open("br") as fd:
                st = self.conn.newStream(0)
                cdrom.upload(st, 0, 1024 * 1024)
                st.send(fd.read())
                st.finish()
            return cdrom

    def prepare_cloud_init_nocloud_iso(self, domain):
        primary_mac_addr = domain.mac_addresses[0]
        self._network_meta = {"config": "disabled"}
        domain.meta_data += CLOUD_INIT_ENI
        domain._network_meta = {
            "version": 1,
            "config": [
                {
                    "type": "physical",
                    "name": "eth0",
                    "mac_address": primary_mac_addr,
                    "subnets": [
                        {
                            "type": "static",
                            "address": str(domain.ipv4),
                            "gateway": str(self.gateway.ip),
                            "dns_nameservers": [str(self.dns.ip)],
                        }
                    ],
                }
            ],
        }

        with tempfile.TemporaryDirectory() as base_temp_dir:
            temp_dir = pathlib.Path(base_temp_dir)
            cd_dir = temp_dir / "cd_dir"
            cd_dir.mkdir()
            user_data_file = cd_dir / "user-data"
            with user_data_file.open("w") as fd:
                fd.write("#cloud-config\n")
                fd.write(yaml.dump(domain.cloud_init, Dumper=yaml.Dumper))
            meta_data_file = cd_dir / "meta-data"
            with meta_data_file.open("w") as fd:
                fd.write(
                    domain.meta_data.format(
                        name=domain.name,
                        ipv4=str(domain.ipv4.ip),
                        gateway=str(self.gateway.ip),
                        network=str(self.network),
                    )
                )
            network_config_file = cd_dir / "network-config"
            with network_config_file.open("w") as fd:
                fd.write(yaml.dump(domain._network_meta, Dumper=yaml.Dumper))

            cidata_file = temp_dir / "{name}-cidata.iso".format(name=domain.name)
            run_cmd(
                [
                    "genisoimage",
                    "-output",
                    cidata_file.name,
                    "-volid",
                    "cidata",
                    "-joliet",
                    "-R",
                    str(cd_dir),
                ],
                cwd=str(temp_dir),
            )

            cdrom = self.create_disk(name=cidata_file.stem, size=1)
            with cidata_file.open("br") as fd:
                st = self.conn.newStream(0)
                cdrom.upload(st, 0, 1024 * 1024)
                st.send(fd.read())
                st.finish()
            return cdrom

    def start(self, domain, metadata_format):
        if metadata_format.get("provider", "") == "nocloud":
            cloud_init_iso = self.prepare_cloud_init_nocloud_iso(domain)
        elif domain.distro.startswith("rhel-6.") or domain.distro.startswith(
            "centos-6."
        ):
            cloud_init_iso = self.prepare_cloud_init_nocloud_iso(domain)
        else:  # OpenStack format is the default
            cloud_init_iso = self.prepare_cloud_init_openstack_iso(domain)

        domain.attachDisk(cloud_init_iso, device="cdrom", disk_type="raw")
        domain.dom.create()
        self.dns_entry(
            libvirt.VIR_NETWORK_UPDATE_COMMAND_DELETE, domain.name, domain.ipv4
        )
        self.dns_entry(
            libvirt.VIR_NETWORK_UPDATE_COMMAND_ADD_FIRST, domain.name, domain.ipv4
        )
        self.dhcp_entry(libvirt.VIR_NETWORK_UPDATE_COMMAND_DELETE, domain.ipv4)
        self.dhcp_entry(
            libvirt.VIR_NETWORK_UPDATE_COMMAND_ADD_FIRST,
            domain.ipv4,
            domain.mac_addresses[0],
        )

    def clean_up(self, domain):
        if domain.ipv4:
            self.dns_entry(
                libvirt.VIR_NETWORK_UPDATE_COMMAND_DELETE, domain.name, domain.ipv4
            )
            self.dhcp_entry(libvirt.VIR_NETWORK_UPDATE_COMMAND_DELETE, domain.ipv4)
        xml = domain.dom.XMLDesc(0)
        state, _ = domain.dom.state()
        if state != libvirt.VIR_DOMAIN_SHUTOFF:
            domain.dom.destroy()
        flag = libvirt.VIR_DOMAIN_UNDEFINE_MANAGED_SAVE
        flag |= libvirt.VIR_DOMAIN_UNDEFINE_SNAPSHOTS_METADATA
        domain.dom.undefineFlags(flag)

        self.storage_pool_obj.refresh()
        root = ET.fromstring(xml)
        for disk in root.findall("./devices/disk[@type='file']/source[@file]"):
            filepath = pathlib.PosixPath(disk.attrib["file"])
            if filepath.exists():
                logger.debug("Purge volume: %s", str(filepath))
                vol = self.storage_pool_obj.storageVolLookupByName(filepath.name)
                vol.delete()

    @property
    def kvm_binary(self):
        paths = [pathlib.PosixPath(i) for i in KVM_BINARIES]
        for i in paths:
            if i.exists():
                return i
        else:
            raise Exception("Failed to find the kvm binary in: ", paths)

    def init_network(self, network_name, network_cidr):
        try:
            self.network_obj = self.conn.networkLookupByName(network_name)
        except libvirt.libvirtError as e:
            if e.get_error_code() != libvirt.VIR_ERR_NO_NETWORK:
                raise (e)

        if not self.network_obj:
            self.network_obj = self.create_network(network_name, network_cidr)

        if not self.network_obj.isActive():
            self.network_obj.create()

        xml = self.network_obj.XMLDesc(0)
        root = ET.fromstring(xml)
        ip = root.find("./ip")

        self.gateway = ipaddress.IPv4Interface(
            "{address}/{netmask}".format(**ip.attrib)
        )
        self.dns = self.gateway
        self.network = self.gateway.network

    def create_network(self, network_name, network_cidr):
        network = ipaddress.ip_network(network_cidr)
        root = ET.fromstring(NETWORK_XML)
        root.find("./name").text = network_name
        root.find("./bridge").attrib["name"] = network_name
        root.find("./ip").attrib = {
            "address": network[1].exploded,
            "netmask": network.netmask.exploded,
        }
        xml = ET.tostring(root).decode()
        return self.conn.networkCreateXML(xml)

    def init_storage_pool(self, storage_pool):
        try:
            self.storage_pool_obj = self.conn.storagePoolLookupByName(storage_pool)
        except libvirt.libvirtError as e:
            if e.get_error_code() != libvirt.VIR_ERR_NO_STORAGE_POOL:
                raise (e)

        storage_dir = pathlib.PosixPath(DEFAULT_STORAGE_DIR)
        if not self.storage_pool_obj:
            self.storage_pool_obj = self.create_storage_pool(
                name=storage_pool, directory=storage_dir
            )

        try:
            full_dir = storage_dir / "upstream"
            dir_exists = full_dir.is_dir()
        except PermissionError:
            dir_exists = False

        if not dir_exists:
            qemu_dir = pathlib.PosixPath(QEMU_DIR)
            logger.error(
                USER_CREATE_STORAGE_POOL_DIR.format(
                    qemu_user=qemu_dir.owner(),
                    qemu_group=qemu_dir.group(),
                    storage_dir=self.get_storage_dir(),
                )
            )
            exit(1)

        if not self.storage_pool_obj.isActive():
            self.storage_pool_obj.create(0)

    def create_storage_pool(self, name, directory):
        root = ET.fromstring(STORAGE_POOL_XML)
        root.find("./name").text = name
        root.find("./target/path").text = str(directory)
        xml = ET.tostring(root).decode()
        pool = self.conn.storagePoolDefineXML(xml, 0)
        if not pool:
            raise Exception("Failed to create pool:", name, xml)
        return pool

    def distro_available(self):
        path = self.get_storage_dir() / "upstream"
        return [path.stem for path in sorted(path.glob("*.qcow2"))]

    def dns_entry(self, command, name, ipv4):
        root = ET.fromstring(NETWORK_HOST_ENTRY)
        root.find("./hostname").text = name
        if command == libvirt.VIR_NETWORK_UPDATE_COMMAND_DELETE and not ipv4:
            return
        root.attrib["ip"] = str(ipv4.ip)
        xml = ET.tostring(root).decode()
        try:
            self.network_obj.update(
                command,
                libvirt.VIR_NETWORK_SECTION_DNS_HOST,
                0,
                xml,
                libvirt.VIR_NETWORK_UPDATE_AFFECT_LIVE,
            )
        except libvirt.libvirtError as e:
            if e.get_error_code() == libvirt.VIR_ERR_OPERATION_INVALID:
                # Already removed
                if command == libvirt.VIR_NETWORK_UPDATE_COMMAND_DELETE:
                    return
            raise

    def dhcp_entry(self, command, ipv4, mac=None):
        root = ET.fromstring(NETWORK_DHCP_ENTRY)
        if mac:
            root.attrib["mac"] = mac
        if command == libvirt.VIR_NETWORK_UPDATE_COMMAND_DELETE and not ipv4:
            return
        root.attrib["ip"] = str(ipv4.ip)
        xml = ET.tostring(root).decode()
        try:
            self.network_obj.update(
                command,
                libvirt.VIR_NETWORK_SECTION_IP_DHCP_HOST,
                0,
                xml,
                libvirt.VIR_NETWORK_UPDATE_AFFECT_LIVE,
            )
        except libvirt.libvirtError as e:
            if e.get_error_code() == libvirt.VIR_ERR_OPERATION_INVALID:
                if command == libvirt.VIR_NETWORK_UPDATE_COMMAND_DELETE:
                    # Already removed
                    return
            raise


class LibvirtDomain:
    def __init__(self, dom):
        self.dom = dom
        self.cloud_init = {
            "resize_rootfs": True,
            "disable_root": 0,
            "bootcmd": [],
            "runcmd": [],
        }
        self.meta_data = (
            "dsmode: local\n" "instance-id: iid-{name}\n" "local-hostname: {name}\n"
        )
        self._ssh_key = None

    @property
    def root_password(self):
        return self.get_metadata("root_password")

    @root_password.setter
    def root_password(self, value):
        self.cloud_init["disable_root"] = False
        self.cloud_init["password"] = value
        self.cloud_init["chpasswd"] = {
            "list": "root:{value}\n".format(value=value),
            "expire": False,
        }
        self.cloud_init["ssh_pwauth"] = True
        self.record_metadata("root_password", value)

    @property
    def ssh_key(self):
        return self._ssh_key

    @ssh_key.setter
    def ssh_key(self, value):
        self._ssh_key = value

    def load_ssh_key_file(self, ssh_key_file):
        doc_url = "https://help.github.com/articles/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent/#generating-a-new-ssh-key"  # NOQA
        try:
            with open(os.path.expanduser(ssh_key_file), "r") as fd:
                self.ssh_key = fd.read()
        except IOError:
            logger.error(
                (
                    "Can not read {filename}. If you don't have any SSH key, "
                    "please follow the steps describe here:\n  {doc_url}"
                ).format(filename=ssh_key_file, doc_url=doc_url)
            )
            raise

        self.cloud_init["ssh_authorized_keys"] = [self.ssh_key]
        if "users" in self.cloud_init:
            self.cloud_init["users"][0]["ssh_authorized_keys"] = [self.ssh_key]

    @property
    def distro(self):
        return self.get_metadata("distro")

    @distro.setter
    def distro(self, distro):
        self.record_metadata("distro", distro)

    @property
    def python_interpreter(self):
        return self.get_metadata("python_interpreter")

    @python_interpreter.setter
    def python_interpreter(self, value):
        self.record_metadata("python_interpreter", value)

    @property
    def username(self):
        return self.get_metadata("username")

    @username.setter
    def username(self, username):
        if not re.match("[a-z_][a-z0-9_-]{1,32}$", username):
            raise Exception("Invalid username: ", username)

        self.cloud_init["users"] = [
            {
                "name": username,
                "gecos": "virt-bootstrap user",
                "sudo": "ALL=(ALL) NOPASSWD:ALL",
                "ssh_authorized_keys": [self.ssh_key],
            }
        ]

        self.record_metadata("username", username)

    @property
    def name(self):
        return self.dom.name()

    @name.setter
    def name(self, name):
        self.dom.rename(name, 0)

    def vcpus(self, value=1):
        self.dom.setVcpusFlags(value, libvirt.VIR_DOMAIN_AFFECT_CONFIG)

    @property
    def memory(self):
        xml = self.dom.XMLDesc(0)
        root = ET.fromstring(xml)
        memory = root.findall("./memory")[0]
        unit = memory.attrib["unit"]

        if unit == "KiB":
            return int(int(memory.text) / 1024)
        elif unit == "MiB":
            return int(int(memory.text))

    @memory.setter
    def memory(self, value):
        if value < 256:
            logger.warning(
                "low memory {value} for VM {name}".format(value=value, name=self.name)
            )
        value *= 1024
        self.dom.setMemoryFlags(
            value, libvirt.VIR_DOMAIN_AFFECT_CONFIG | libvirt.VIR_DOMAIN_MEM_MAXIMUM
        )
        self._memory = value

    def getNextBlckDevice(self):
        if not hasattr(self, "blockdev"):
            self.blockdev = list(string.ascii_lowercase)
            self.blockdev.reverse()
        return "vd{block}".format(block=self.blockdev.pop())

    def record_metadata(self, k, v):
        meta = "<{k} name='{v}' />".format(k=k, v=v)
        self.dom.setMetadata(
            libvirt.VIR_DOMAIN_METADATA_ELEMENT,
            meta,
            "vl",
            k,
            libvirt.VIR_DOMAIN_AFFECT_CONFIG,
        )

    def get_metadata(self, k):
        try:
            xml = self.dom.metadata(libvirt.VIR_DOMAIN_METADATA_ELEMENT, k)
        except libvirt.libvirtError as e:
            if e.get_error_code() == libvirt.VIR_ERR_NO_DOMAIN_METADATA:
                return None
            raise (e)
        elt = ET.fromstring(xml)
        return elt.attrib["name"]

    @property
    def context(self):
        return self.get_metadata("context")

    @context.setter
    def context(self, value):
        self.record_metadata("context", value)

    @property
    def groups(self):
        value = self.get_metadata("groups")
        if not value:
            return []
        return value.split(",")

    @groups.setter
    def groups(self, value):
        self.record_metadata("groups", ",".join(value))

    def attachDisk(self, volume, device="disk", disk_type="qcow2"):
        if device == "cdrom":
            bus = "ide"
        elif self.distro.startswith("esxi"):
            bus = "sata"
        else:
            bus = "virtio"
        device_name = self.getNextBlckDevice()
        disk_root = ET.fromstring(DISK_XML)
        disk_root.attrib["device"] = device
        disk_root.findall("./driver")[0].attrib = {"name": "qemu", "type": disk_type}
        disk_root.findall("./source")[0].attrib = {"file": volume.path()}
        disk_root.findall("./target")[0].attrib = {"dev": device_name, "bus": bus}
        xml = ET.tostring(disk_root).decode()
        self.dom.attachDeviceFlags(xml, libvirt.VIR_DOMAIN_AFFECT_CONFIG)
        return device_name

    def attachNetwork(self, network=None):
        disk_root = ET.fromstring(BRIDGE_XML)
        disk_root.findall("./source")[0].attrib = {"network": network}
        if self.distro.startswith("esxi"):
            disk_root.findall("./model")[0].attrib = {"type": "e1000"}

        xml = ET.tostring(disk_root).decode()
        self.dom.attachDeviceFlags(xml, libvirt.VIR_DOMAIN_AFFECT_CONFIG)

    def add_root_disk(self, root_disk_path):
        self.attachDisk(root_disk_path)

    def add_swap_disk(self, swap_path):
        device_name = self.attachDisk(swap_path)
        self.cloud_init["mounts"] = [[device_name, "none", "swap", "sw", 0, 0]]
        self.cloud_init["bootcmd"].append("mkswap /dev/vdb")
        self.cloud_init["bootcmd"].append("swapon /dev/vdb")

    @property
    def ipv4(self):
        if self.get_metadata("ipv4"):
            return ipaddress.IPv4Interface(self.get_metadata("ipv4"))

    @ipv4.setter
    def ipv4(self, value):
        self.record_metadata("ipv4", value)

    @property
    def mac_addresses(self):
        xml = self.dom.XMLDesc(0)
        root = ET.fromstring(xml)
        ifaces = root.findall("./devices/interface/mac[@address]")
        return [iface.attrib["address"] for iface in ifaces]

    def set_user_password(self, user, password):
        return self.dom.setUserPassword(user, password)

    def __gt__(self, other):
        return self.name > other.name

    def __lt__(self, other):
        return self.name < other.name

    async def reachable(self):
        while True:
            try:
                reader, _ = await asyncio.open_connection(str(self.ipv4.ip), 22)
                data = await reader.read(10)
                if data.decode().startswith("SSH"):
                    logger.info(
                        "{computer} {name} found at {ipv4}!".format(
                            computer=symbols.COMPUTER.value,
                            name=self.name,
                            ipv4=self.ipv4.ip,
                        )
                    )
                    return
            except (OSError, ConnectionRefusedError):
                pass
        await asyncio.sleep(0.2)

    def exec_ssh(self):
        os.execlp(
            "ssh",
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "{username}@{ipv4}".format(username=self.username, ipv4=self.ipv4.ip),
        )
