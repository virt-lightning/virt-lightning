#!/usr/bin/env python3

from __future__ import annotations

import asyncio
import getpass
import ipaddress
import json
import logging
import math
import os
import pathlib
import re
import string
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET  # noqa: N817

import libvirt
import yaml

from virt_lightning.metadata import (
    CloudInit22UserData,
    CloudInit23UserData,
    DomainConfig,
    OpenStackUserData,
    UserData,
)
from virt_lightning.symbols import get_symbols

from .templates import (
    BRIDGE_XML,
    DISK_XML,
    DOMAIN_XML,
    NETWORK_DHCP_ENTRY,
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
ISO_BINARIES = (
    "genisoimage",
    "mkisofs",
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
    return outs


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

    def create_domain(self, name=None, distro=None) -> LibvirtDomain:
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

    def configure_domain(self, domain: LibvirtDomain, user_config: DomainConfig) -> DomainConfig:
        """
        Apply configuration to a domain.

        Merges user_config with distro-specific defaults. User-supplied values
        (non-None/non-empty) override distro defaults.

        Args:
            domain: The LibvirtDomain to configure
            user_config: User-provided configuration that overrides distro defaults

        Returns:
            The merged DomainConfig
        """
        distro_config = self.get_distro_configuration(domain.distro)
        config = user_config.merge_with(distro_config)

        # TODO: move all of these to nested object
        domain.groups = config.groups
        domain.memory = config.memory
        domain.python_interpreter = config.python_interpreter
        domain.root_password = config.root_password
        domain.username = config.username
        domain.vcpus = config.vcpus
        domain.default_nic_model = config.default_nic_model
        domain.bootcmd = config.bootcmd
        domain.runcmd = config.runcmd
        domain.meta_data_media_type = config.meta_data_media_type
        domain.default_bus_type = config.default_bus_type
        domain.fqdn = config.fqdn
        if config.ssh_key_file:
            domain.load_ssh_key_file(config.ssh_key_file)
        return config

    def get_distro_configuration(self, distro: str) -> DomainConfig:
        distro_configuration_file = pathlib.PosixPath(
            f"{self.get_storage_dir()}/upstream/{distro}.yaml"
        )
        if not distro_configuration_file.exists():
            return DomainConfig()
        config: dict = (
            yaml.load(distro_configuration_file.open("r"), Loader=yaml.SafeLoader) or {}
        )
        return DomainConfig(**config)

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
            cidr_ip = f"{ip}/24"
            interface = ipaddress.IPv4Interface(cidr_ip)
            if int(interface.ip.exploded.split(".")[3]) < 5:
                continue
            if self._last_free_ipv4 and self._last_free_ipv4 >= interface:
                continue
            if interface.ip not in [i.ip for i in used_ips]:
                self._last_free_ipv4 = interface
                return interface

    def get_storage_dir(self):
        xml = self.storage_pool_obj.XMLDesc(0)
        root = ET.fromstring(xml)
        disk_source = root.find("./target/path")
        return pathlib.PosixPath(disk_source.text)

    def get_qcow_virtual_size(self, qcow_path):
        qemu_img_info = run_cmd(["qemu-img", "info", "--output=json", str(qcow_path)])
        return math.ceil(json.loads(qemu_img_info)["virtual-size"] / 1024**3)

    def create_disk(self, name, size=None, backing_on=None):
        backing_file = None
        min_size = 0
        if backing_on:
            backing_file = pathlib.PosixPath(
                f"{self.get_storage_dir()}/upstream/{backing_on}.qcow2"
            )
            min_size = self.get_qcow_virtual_size(backing_file)
        disk_path = pathlib.PosixPath(f"{self.get_storage_dir()}/{name}.qcow2")

        if "/" in name:
            raise TypeError
        if not size:
            size = 20
        if size < min_size:
            size = min_size
            logger.debug(
                "Increasing the size of the image to match the backing image size: %s (%dGB)",
                str(disk_path),
                size,
            )

        logger.debug("create_disk: %s (%dGB)", str(disk_path), size)
        root = ET.fromstring(STORAGE_VOLUME_XML)
        root.find("./name").text = disk_path.name
        root.find("./capacity").text = str(size)
        root.find("./target/path").text = str(disk_path)

        if backing_file:
            backing = ET.SubElement(root, "backingStore")
            ET.SubElement(backing, "path").text = str(backing_file)
            ET.SubElement(backing, "format").attrib = {"type": "qcow2"}

        xml = ET.tostring(root).decode()
        try:
            return self.storage_pool_obj.createXML(xml)
        except libvirt.libvirtError as e:
            if e.get_error_code() == libvirt.VIR_ERR_STORAGE_VOL_EXIST:
                logger.error(
                    f"A volume image already exists and prevent the creation "
                    f" of a new one. You can remove it with the following "
                    f"command:\n"
                    f"  sudo virsh vol-delete --pool "
                    f"{self.storage_pool_obj.name()} {name}.qcow2"
                )
                sys.exit(1)
            raise

    def start(self, domain: LibvirtDomain, config: DomainConfig) -> None:
        userdata = self._create_userdata(domain, config)
        with tempfile.TemporaryDirectory() as temp_dir:
            iso_path = userdata.build_iso(domain.name, self.iso_binary, pathlib.Path(temp_dir))
            cloud_init_iso = self.create_disk(name=iso_path.stem, size=1)
            with iso_path.open("br") as fd:
                st = self.conn.newStream(0)
                cloud_init_iso.upload(st, 0, 1024 * 1024)
                st.send(fd.read())
                st.finish()

        media_type = domain.meta_data_media_type
        domain.attach_disk(cloud_init_iso, device=media_type, disk_type="raw")
        domain.dom.create()
        self.remove_domain_from_network(domain)
        self.add_domain_to_network(domain)

    def _create_userdata(self, domain: LibvirtDomain, config: DomainConfig) -> UserData:
        if config.datasource == "nocloud":
            if int(config.cloudinit_version.split(".")[0]) >= 23:
                return CloudInit23UserData.from_domain(domain, self)
            return CloudInit22UserData.from_domain(domain, self)
        return OpenStackUserData.from_domain(domain, self)

    def add_domain_to_network(self, domain):
        self.set_dns_entry(domain.ipv4, [domain.name, domain.fqdn])
        self.set_dhcp_entry(domain.ipv4, domain.nics[0]["mac"])

    def remove_domain_from_network(self, domain):
        root = ET.fromstring(self.network_obj.XMLDesc(0))
        if not domain.ipv4:
            return
        for host in root.findall("./dns/host[@ip]"):
            if host.attrib["ip"] != str(domain.ipv4.ip):
                continue
            xml = ET.tostring(host, encoding="unicode")
            self.network_obj.update(
                libvirt.VIR_NETWORK_UPDATE_COMMAND_DELETE,
                libvirt.VIR_NETWORK_SECTION_DNS_HOST,
                0,
                xml,
                libvirt.VIR_NETWORK_UPDATE_AFFECT_LIVE,
            )

        root = ET.fromstring(self.network_obj.XMLDesc(0))
        for host in root.findall("./ip/dhcp/host[@ip]"):
            if host.attrib["ip"] != str(domain.ipv4.ip):
                continue
            xml = ET.tostring(host, encoding="unicode")
            self.network_obj.update(
                libvirt.VIR_NETWORK_UPDATE_COMMAND_DELETE,
                libvirt.VIR_NETWORK_SECTION_IP_DHCP_HOST,
                0,
                xml,
                libvirt.VIR_NETWORK_UPDATE_AFFECT_LIVE,
            )

        domain_root = ET.fromstring(domain.dom.XMLDesc(0))
        ifaces = domain_root.findall("./devices/interface/mac[@address]")
        domain_macs = [iface.attrib["address"] for iface in ifaces]

        root = ET.fromstring(self.network_obj.XMLDesc(0))
        for host in root.findall("./ip/dhcp/host[@mac]"):
            if host.attrib["mac"] not in domain_macs:
                continue
            xml = ET.tostring(host, encoding="unicode")
            self.network_obj.update(
                libvirt.VIR_NETWORK_UPDATE_COMMAND_DELETE,
                libvirt.VIR_NETWORK_SECTION_IP_DHCP_HOST,
                0,
                xml,
                libvirt.VIR_NETWORK_UPDATE_AFFECT_LIVE,
            )

    def clean_up(self, domain):
        self.remove_domain_from_network(domain)
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
        raise Exception("Failed to find the kvm binary in: ", paths)

    @property
    def iso_binary(self):
        # TODO: Make this more testable - consider making it an injectable dependency
        # or extracting to a separate utility class to avoid PropertyMock in tests
        paths = [pathlib.PosixPath(i) for i in os.environ["PATH"].split(os.pathsep)]
        for i in paths:
            for binary in ISO_BINARIES:
                exe = i / binary
                if exe.exists():
                    return exe
        error_msg = (
            f"Failed to find {' or '.join(ISO_BINARIES)} in "
            f"{', '.join([x.as_posix() for x in paths])} "
            "\nPlease install genisoimage tool"
        )
        raise Exception(error_msg)

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
        self.gateway = self.get_network_gateway(network_name)
        self.dns = self.gateway
        self.network = self.gateway.network

    def get_network_by_name(self, network_name):
        try:
            return self.conn.networkLookupByName(network_name)
        except libvirt.libvirtError as e:
            if e.get_error_code() != libvirt.VIR_ERR_NO_NETWORK:
                raise (e)

    def get_network_gateway(self, network_name):
        network_obj = self.get_network_by_name(network_name)
        xml = network_obj.XMLDesc(0)
        root = ET.fromstring(xml)
        ip = root.find("./ip")
        return ipaddress.IPv4Interface("{address}/{netmask}".format(**ip.attrib))

    def reuse_mac_address(self, network_name, domain_name, ipv4):
        network_obj = self.get_network_by_name(network_name)
        for lease in network_obj.DHCPLeases():
            if lease["hostname"] == domain_name and lease["ipaddr"] == str(ipv4.ip):
                return lease["mac"]

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
                USER_CREATE_STORAGE_POOL_DIR.format(  # noqa: G001
                    user=getpass.getuser(),
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

    def set_dns_entry(self, ipv4, names=None):
        root = ET.fromstring(NETWORK_HOST_ENTRY)
        for name in names:
            if name:
                ET.SubElement(root, "hostname").text = name
        root.attrib["ip"] = str(ipv4.ip)
        xml = ET.tostring(root).decode()
        self.network_obj.update(
            libvirt.VIR_NETWORK_UPDATE_COMMAND_ADD_FIRST,
            libvirt.VIR_NETWORK_SECTION_DNS_HOST,
            0,
            xml,
            libvirt.VIR_NETWORK_UPDATE_AFFECT_LIVE,
        )

    def set_dhcp_entry(self, ipv4, mac=None):
        root = ET.fromstring(NETWORK_DHCP_ENTRY)
        root.attrib["mac"] = mac
        root.attrib["ip"] = str(ipv4.ip)
        xml = ET.tostring(root).decode()
        self.network_obj.update(
            libvirt.VIR_NETWORK_UPDATE_COMMAND_ADD_FIRST,
            libvirt.VIR_NETWORK_SECTION_IP_DHCP_HOST,
            0,
            xml,
            libvirt.VIR_NETWORK_UPDATE_AFFECT_LIVE,
        )


class LibvirtDomain:
    def __init__(self, dom):
        self.dom = dom
        self.user_data = {
            "resize_rootfs": True,
            "disable_root": 0,
            "bootcmd": [],
            "runcmd": [],
        }
        self._ssh_key = None
        self.default_nic_model = None
        self.nics = []
        self.meta_data_media_type = None
        self.default_bus_type = None

    @property
    def root_password(self):
        return self.get_metadata("root_password")

    @root_password.setter
    def root_password(self, value):
        self.user_data["disable_root"] = False
        self.user_data["password"] = value
        self.user_data["chpasswd"] = {
            "list": f"root:{value}\n",
            "expire": False,
        }
        self.user_data["ssh_pwauth"] = True
        self.record_metadata("root_password", value)

    @property
    def ssh_key(self):
        return self._ssh_key

    @ssh_key.setter
    def ssh_key(self, value):
        self._ssh_key = value

    def load_ssh_key_file(self, ssh_key_file):
        doc_url = "https://help.github.com/articles/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent/#generating-a-new-ssh-key"
        path = pathlib.Path(ssh_key_file) if isinstance(ssh_key_file, str) else ssh_key_file
        try:
            self.ssh_key = path.expanduser().read_text()
        except OSError:
            logger.error(
                f"Can not read {ssh_key_file}. If you don't have any SSH key, "
                f"please follow the steps describe here:\n  {doc_url}"
                "\n"
                "If you're SSH key is not ~/.ssh/id_rsa.pub, you need to configure "
                "the ~/.config/virt-lightning/config.ini file, e.g:\n"
                "\n"
                "[main]\n"
                "ssh_key_file = ~/.ssh/id_ed25519.pub\n"
            )
            raise

        self.user_data["ssh_authorized_keys"] = [self.ssh_key]
        if "users" in self.user_data:
            self.user_data["users"][0]["ssh_authorized_keys"] = [self.ssh_key]

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
            raise ValueError("Invalid username: ", username)

        self.user_data["users"] = [
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
        self.user_data["name"] = name
        self.dom.rename(name, 0)

    @property
    def fqdn(self):
        return self.get_metadata("fqdn")

    @fqdn.setter
    def fqdn(self, value):
        fqdn_validate = re.compile(r"^[\.a-z0-9]+$", re.IGNORECASE)
        if not value or not fqdn_validate.match(value):
            logger.error(f"Invalid FQDN: {value}")
            return
        self.user_data["fqdn"] = value
        self.record_metadata("fqdn", value)

    @property
    def vcpus(self):
        xml = self.dom.XMLDesc(0)
        root = ET.fromstring(xml)
        vcpu = root.findall("./vcpu")[0]
        return int(vcpu.attrib.get("current", vcpu.text))

    @vcpus.setter
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
            logger.warning(f"low memory: {value}MB for VM {self.name}")
        value *= 1024
        self.dom.setMemoryFlags(
            value, libvirt.VIR_DOMAIN_AFFECT_CONFIG | libvirt.VIR_DOMAIN_MEM_MAXIMUM
        )
        self.dom.setMemoryFlags(value, libvirt.VIR_DOMAIN_AFFECT_CONFIG)

    def get_next_block_device(self):
        if not hasattr(self, "blockdev"):
            self.blockdev = list(string.ascii_lowercase)
            self.blockdev.reverse()
        return f"vd{self.blockdev.pop()}"

    def record_metadata(self, k, v):
        meta = f"<{k} name='{v}' />"
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

    def attach_disk(self, volume, device="disk", disk_type="qcow2"):
        if device == "cdrom":  # noqa: SIM108
            # virtio does not support ejectable media
            bus = "ide"
        else:
            bus = self.default_bus_type or "virtio"

        device_name = self.get_next_block_device()
        disk_root = ET.fromstring(DISK_XML)
        disk_root.attrib["device"] = device
        disk_root.findall("./driver")[0].attrib = {"name": "qemu", "type": disk_type}
        disk_root.findall("./source")[0].attrib = {"file": volume.path()}
        disk_root.findall("./target")[0].attrib = {"dev": device_name, "bus": bus}
        xml = ET.tostring(disk_root).decode()
        self.dom.attachDeviceFlags(xml, libvirt.VIR_DOMAIN_AFFECT_CONFIG)
        return device_name

    def attach_network(
        self,
        network=None,
        nic_model=None,
        ipv4=None,
        mac=None,
        bridge=None,
        virtualport_type=None,
    ):
        if not nic_model:
            nic_model = self.default_nic_model
        net_root = ET.fromstring(BRIDGE_XML)

        if bridge:
            source_attrs = {"bridge": bridge}
            net_root.attrib["type"] = "bridge"
        elif network:
            source_attrs = {"network": network}
        net_root.findall("./source")[0].attrib = source_attrs
        net_root.findall("./model")[0].attrib = {"type": nic_model}

        if virtualport_type:
            net_root.append(ET.Element("virtualport", type=virtualport_type))

        if mac:
            mac_el = ET.SubElement(net_root, "mac")
            mac_el.attrib = {"address": mac}

        if not ipv4:
            if not self.nics:
                raise ValueError("First NIC should have a static IPv4 address.")
            ipv4_instance = None  # DHCP
        elif isinstance(ipv4, ipaddress.IPv4Interface):
            ipv4_instance = ipv4
        elif ipv4 and "/" not in ipv4:
            ipv4_instance = ipaddress.IPv4Interface(ipv4 + "/24")
        elif ipv4:
            ipv4_instance = ipaddress.IPv4Interface(ipv4)
        self.nics.append({"network": network, "ipv4": ipv4_instance})

        # add metadata for the additional NICs
        if len(self.nics) > 1:
            add_nics = self.additional_nics or ""
            add_nics += f"{network}_ipv4={ipv4_instance} "
            self.additional_nics = add_nics

        self.ipv4 = self.nics[0]["ipv4"]

        xml = ET.tostring(net_root).decode()
        self.dom.attachDeviceFlags(xml, libvirt.VIR_DOMAIN_AFFECT_CONFIG)

        xml = self.dom.XMLDesc(0)
        root = ET.fromstring(xml)
        ifaces = root.findall("./devices/interface/mac[@address]")
        for i, iface in enumerate(ifaces):
            self.nics[i]["mac"] = iface.attrib["address"]

    def add_root_disk(self, root_disk_path):
        self.attach_disk(root_disk_path)

    @property
    def ipv4(self):
        if self.get_metadata("ipv4"):
            return ipaddress.IPv4Interface(self.get_metadata("ipv4"))

    @ipv4.setter
    def ipv4(self, value):
        self.record_metadata("ipv4", value)

    @property
    def additional_nics(self):
        if self.get_metadata("additional_nics"):
            return self.get_metadata("additional_nics")

    @additional_nics.setter
    def additional_nics(self, value):
        self.record_metadata("additional_nics", value)

    @property
    def bootcmd(self):
        return self.user_data["bootcmd"]

    @bootcmd.setter
    def bootcmd(self, value):
        if not hasattr(value, "append"):
            raise ValueError("bootcmd should be a list of command")
        self.user_data["bootcmd"] = value

    @property
    def runcmd(self):
        return self.user_data["runcmd"]

    @runcmd.setter
    def runcmd(self, value):
        if not hasattr(value, "append"):
            raise ValueError("runcmd should be a list of command")
        self.user_data["runcmd"] = value

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
                        f"{symbols.COMPUTER.value} {self.name} found at {self.ipv4.ip}!"
                    )
                    return
            except OSError:
                pass

    def exec_ssh(self):
        os.execlp(
            "ssh",
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            f"{self.username}@{self.ipv4.ip}",
        )
