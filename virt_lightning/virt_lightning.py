#!/usr/bin/env python3

import ipaddress
import os
import pathlib
import re
import string
import subprocess
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET

import libvirt

import netifaces

import yaml


from .templates import (
    BRIDGE_XML,
    CLOUD_INIT_ENI,
    DISK_XML,
    DOMAIN_XML,
    STORAGE_POOL_XML,
    USER_CREATE_STORAGE_POOL_DIR,
)

KVM_BINARIES = ("/usr/bin/qemu-kvm", "/usr/bin/kvm")


def libvirt_callback(userdata, err):
    pass


libvirt.registerErrorHandler(f=libvirt_callback, ctx=None)


def run_cmd(cmd, cwd=None):
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd
    )
    outs, errs = proc.communicate()
    if proc.returncode != 0:
        raise Exception("A command has failed: ", outs, errs)


class LibvirtHypervisor:
    def __init__(self, libvirt_uri):
        conn = libvirt.open(libvirt_uri)

        if conn is None:
            error_tpl = "Failed to open connection to {uri}"
            print(error_tpl.format(uri=libvirt_uri))
            exit(1)

        self.conn = conn
        self._last_free_ipv4 = None
        self.wait_for = []

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
            print("kvm mode not available!")
        # Sorted to get kvm before qemu, assume there is no other type
        return sorted(available)[0]

    def create_domain(self, name=None, distro=None):
        if not name:
            name = uuid.uuid4().hex[0:10]
        root = ET.fromstring(DOMAIN_XML)
        root.attrib["type"] = self.domain_type
        root.find("./name").text = name
        root.find("./devices/emulator").text = str(self.kvm_binary)
        root.find("./os/type").attrib["arch"] = self.arch
        dom = self.conn.defineXML(ET.tostring(root).decode())
        domain = LibvirtDomain(dom)
        domain.distro = distro
        return domain

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
                raise (e)

    def get_free_ipv4(self):
        # TODO: extend the list with ARP table
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

    def create_disk(self, name, size=20, backing_on=None):
        disk_path = "{path}/{name}.qcow2".format(path=self.get_storage_dir(), name=name)
        cmd = ["qemu-img", "create", "-f", "qcow2"]
        if backing_on:
            backing_disk = "{path}/upstream/{name}.qcow2".format(
                path=self.get_storage_dir(), name=backing_on
            )
            cmd += ["-b", backing_disk]
        cmd += [disk_path, "{size}G".format(size=size)]

        run_cmd(cmd)
        return disk_path

    def prepare_meta_data(self, domain):
        cidata_path = "{path}/{name}-cidata.iso".format(
            path=self.get_storage_dir(), name=domain.name
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            with open(temp_dir + "/user-data", "w") as fd:
                fd.write("#cloud-config\n")
                fd.write(yaml.dump(domain.cloud_init, Dumper=yaml.Dumper))
            with open(temp_dir + "/meta-data", "w") as fd:
                fd.write(
                    domain.meta_data.format(
                        name=domain.name,
                        ipv4=str(domain.ipv4.ip),
                        gateway=str(domain.gateway.ip),
                    )
                )
            with open(temp_dir + "/network-config", "w") as fd:
                fd.write(yaml.dump(domain._network_meta, Dumper=yaml.Dumper))

            run_cmd(
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
                    "network-config",
                ],
                cwd=temp_dir,
            )
        return cidata_path

    def start(self, domain):
        meta_data_iso = self.prepare_meta_data(domain)
        domain.attachDisk(meta_data_iso, device="cdrom", disk_type="raw")
        domain.dom.create()

    def clean_up(self, domain):
        xml = domain.dom.XMLDesc(0)
        state, _ = domain.dom.state()
        if state != libvirt.VIR_DOMAIN_SHUTOFF:
            domain.dom.destroy()
        flag = libvirt.VIR_DOMAIN_UNDEFINE_MANAGED_SAVE
        flag |= libvirt.VIR_DOMAIN_UNDEFINE_SNAPSHOTS_METADATA
        domain.dom.undefineFlags(flag)

        root = ET.fromstring(xml)
        for disk in root.findall("./devices/disk[@type='file']/source[@file]"):
            filepath = disk.attrib["file"]
            try:
                self.conn.storageVolLookupByPath(filepath).delete()
            except libvirt.libvirtError as e:
                if e.get_error_code() == libvirt.VIR_ERR_NO_STORAGE_VOL:
                    pass

    @property
    def kvm_binary(self):
        paths = [pathlib.PosixPath(i) for i in KVM_BINARIES]
        for i in paths:
            if i.exists():
                return i
        else:
            raise Exception("Failed to find the kvm binary in: ", paths)

    def init_network(self, bridge_name):
        try:
            bridge_netiface = netifaces.ifaddresses(bridge_name)
        except ValueError:
            print("Bridge not found:", bridge_name)
            exit(1)
        ipconfig = bridge_netiface[netifaces.AF_INET]
        self.gateway = ipaddress.IPv4Interface("{addr}/{netmask}".format(**ipconfig[0]))
        self.dns = self.gateway
        self.network = self.gateway.network

    def init_storage_pool(self, storage_pool):
        try:
            self.storage_pool_obj = self.conn.storagePoolLookupByName(storage_pool)
            if not self.get_storage_dir().is_dir():
                raise Exception("Missing storage directory:", self.get_storage_dir())
            if not self.storage_pool_obj.isActive():
                self.storage_pool_obj.create(0)
            return
        except libvirt.libvirtError as e:
            if e.get_error_code() == libvirt.VIR_ERR_NO_STORAGE_POOL:
                pass

        if self.conn.getURI().startswith("qemu:///system"):
            storage_dir = pathlib.PosixPath("/var/lib/virt-lightning/pool")
        elif self.conn.getURI().startswith("qemu:///session"):
            storage_dir = pathlib.PosixPath("~/.local/share/virt-lightning/pool")
            storage_dir = storage_dir.expanduser()
        else:
            raise Exception("Unsupported libvirt URI")

        full_dir = storage_dir / "upstream"
        try:
            full_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            qemu_dir = pathlib.PosixPath("/var/lib/libvirt/qemu/")
            print(
                USER_CREATE_STORAGE_POOL_DIR.format(
                    qemu_user=qemu_dir.owner(),
                    qemu_group=qemu_dir.group(),
                    storage_dir=storage_dir,
                )
            )
            exit(1)
        self.storage_pool_obj = self.create_storage_pool(
            name=storage_pool, directory=storage_dir
        )

    def create_storage_pool(self, name, directory):
        root = ET.fromstring(STORAGE_POOL_XML)
        root.find("./name").text = name
        root.find("./target/path").text = str(directory)
        xml = ET.tostring(root).decode()
        pool = self.conn.storagePoolDefineXML(xml, 0)
        if not pool:
            raise Exception("Failed to create pool:", name, xml)
        pool.setAutostart(1)
        pool.create(0)
        return pool

    def distro_available(self):
        path = self.get_storage_dir() / "upstream"
        return [path.stem for path in sorted(path.glob("*.qcow2"))]


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
        self.distro = None
        self._ssh_key = None

    @property
    def root_password(self):
        return self.cloud_init.get("password")

    @root_password.setter
    def root_password(self, value):
        self.cloud_init["disable_root"] = False
        self.cloud_init["password"] = value
        self.cloud_init["chpasswd"] = {"expire": False}
        self.cloud_init["ssh_pwauth"] = True

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
            raise Exception(
                (
                    "Can not read {filename}. If you don't have any SSH key, "
                    "please follow the steps describe here:\n  {doc_url}"
                ).format(filename=ssh_key_file, doc_url=doc_url)
            )

        self.cloud_init["ssh_authorized_keys"] = [self.ssh_key]
        if "users" in self.cloud_init:
            self.cloud_init["users"][0]["ssh_authorized_keys"] = [self.ssh_key]

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
                "ssh_authorized_keys": self.ssh_key,
            }
        ]

        self.record_metadata("username", username)

    @property
    def name(self):
        return self.dom.name()

    @name.setter
    def name(self, name):
        self.dom.rename(name, 0)

    def vcpus(self, value=None):
        if value:
            self.dom.setVcpusFlags(value, libvirt.VIR_DOMAIN_AFFECT_CONFIG)

    def memory(self, value=None):
        if value:
            if value < 256:
                print(
                    "Warning: low memory {value} for VM {name}".format(
                        value=value, name=self.name
                    )
                )
            value *= 1024
            self.dom.setMemoryFlags(
                value, libvirt.VIR_DOMAIN_AFFECT_CONFIG | libvirt.VIR_DOMAIN_MEM_MAXIMUM
            )

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

    def add_root_disk(self, root_disk_path):
        self.attachDisk(root_disk_path)

    def add_swap_disk(self, swap_path):
        device_name = self.attachDisk(swap_path)
        self.cloud_init["mounts"] = [device_name, "none", "swap", "sw", 0, 0]
        self.cloud_init["bootcmd"].append("mkswap /dev/vdb")
        self.cloud_init["bootcmd"].append("swapon /dev/vdb")

    def set_ip(self, ipv4, gateway, dns):
        self.ipv4 = ipv4
        self.gateway = gateway
        self.dns = dns
        self.record_metadata("ipv4", ipv4)

        primary_mac_addr = self.mac_addresses[0]
        self._network_meta = {"config": "disabled"}
        if "ubuntu-18.04" in self.distro:
            self._network_meta = {
                "version": 2,
                "ethernets": {
                    "interface0": {
                        "match": {"macaddress": primary_mac_addr},
                        "set-name": "interface0",
                        "addresses": [str(self.ipv4)],
                        "gateway4": str(self.gateway.ip),
                        "nameservers": {"addresses": [str(self.dns.ip)]},
                    }
                },
            }
        else:
            self.meta_data += CLOUD_INIT_ENI
            self._network_meta = {
                "version": 1,
                "config": [
                    {
                        "type": "physical",
                        "name": "eth0",
                        "mac_address": primary_mac_addr,
                        "subnets": [
                            {
                                "type": "static",
                                "address": str(self.ipv4),
                                "gateway": str(self.gateway.ip),
                                "dns_nameservers": [str(self.dns.ip)],
                            }
                        ],
                    }
                ],
            }
        nm_filter = "(centos|fedora|rhel)"
        if re.match(nm_filter, self.distro):
            nmcli_call = (
                "nmcli c add type ethernet con-name eth0 ifname eth0 ip4 {ipv4} "
                "ipv4.gateway {gateway} ipv4.dns {dns} ipv4.method manual"
            )
            self.cloud_init["runcmd"].append("nmcli -g UUID c|xargs -n 1 nmcli con del")
            self.cloud_init["runcmd"].append(
                nmcli_call.format(
                    ipv4=self.ipv4, gateway=str(self.gateway.ip), dns=str(self.dns.ip)
                )
            )
            # Without that NM, initialize eth0 with a DHCP IP
            self.cloud_init["bootcmd"].append(
                'echo "[main]" > /etc/NetworkManager/conf.d/no-auto-default.conf'
            )
            self.cloud_init["bootcmd"].append(
                (
                    'echo "no-auto-default=eth0" >> '
                    "/etc/NetworkManager/conf.d/no-auto-default.conf"
                )
            )

    @property
    def mac_addresses(self):
        xml = self.dom.XMLDesc(0)
        root = ET.fromstring(xml)
        ifaces = root.findall("./devices/interface/mac[@address]")
        return [iface.attrib["address"] for iface in ifaces]

    def get_ipv4(self):
        if not self.dom.isActive():
            return
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
        except libvirt.libvirtError as e:
            if e.get_error_code() == libvirt.VIR_ERR_AGENT_UNRESPONSIVE:
                pass
            else:
                print(e.get_error_code())
                raise (e)

    def set_user_password(self, user, password):
        return self.dom.setUserPassword(user, password)

    def ssh_ping(self):
        if hasattr(self, "_ssh_ping"):
            return self._ssh_ping
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
                "-o",
                "ConnectTimeout=1",
                "{username}@{ipv4}".format(username=self.username, ipv4=ipv4),
                "hostname",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(1)
        status = proc.poll()
        proc.kill()
        if status == 0:
            self._ssh_ping = True
            return True
        else:
            return False

    def __gt__(self, other):
        return self.name > other.name

    def __lt__(self, other):
        return self.name < other.name
