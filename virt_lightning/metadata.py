from dataclasses import dataclass, field, asdict
from typing import Optional, List, Any, TYPE_CHECKING
from dataclasses import fields, MISSING
from abc import ABC, abstractmethod
from pathlib import Path
from ipaddress import IPv4Interface
import json
import logging
import subprocess
import yaml

if TYPE_CHECKING:
    from virt_lightning.virt_lightning import LibvirtDomain, LibvirtHypervisor

logger = logging.getLogger(__name__)


@dataclass
class NetworkInterface:
    """One NIC's configuration, format-agnostic."""
    name: str  # e.g. "eth0"
    mac: str
    ipv4: Optional[IPv4Interface]  # None → DHCP
    gateway: Optional[IPv4Interface]
    dns_nameservers: List[str]


class UserData(ABC):
    """Universal internal representation of all data injected into a VM."""

    def __init__(
        self,
        hostname: str,
        fqdn: Optional[str],
        instance_id: str,
        ssh_public_key: str,
        root_password: Optional[str],
        username: str,
        interfaces: List[NetworkInterface],
        global_dns: List[str],
        cloud_config: dict,
    ):
        self.hostname = hostname
        self.fqdn = fqdn
        self.instance_id = instance_id
        self.ssh_public_key = ssh_public_key
        self.root_password = root_password
        self.username = username
        self.interfaces = interfaces
        self.global_dns = global_dns
        self.cloud_config = cloud_config  # the user_data dict

    @classmethod
    def from_domain(
        cls, domain: "LibvirtDomain", hv: "LibvirtHypervisor"
    ) -> "UserData":
        """Construct from existing domain state — factory to be called by subclasses."""
        interfaces = []
        for i, nic in enumerate(domain.nics):
            gateway = hv.get_network_gateway(nic["network"])
            interfaces.append(
                NetworkInterface(
                    name=f"eth{i}",
                    mac=nic["mac"],
                    ipv4=nic["ipv4"],
                    gateway=gateway,
                    dns_nameservers=[str(hv.dns.ip)],
                )
            )
        return cls(
            hostname=domain.name,
            fqdn=domain.fqdn,
            instance_id=domain.dom.UUIDString(),
            ssh_public_key=domain.ssh_key,
            root_password=domain.root_password,
            username=domain.username,
            interfaces=interfaces,
            global_dns=[str(hv.dns.ip)],
            cloud_config=domain.user_data,
        )

    @abstractmethod
    def render(self, output_dir: Path) -> None:
        """Write format-specific files into output_dir."""
        ...

    @abstractmethod
    def iso_label(self) -> str:
        """Return the ISO volume label."""
        ...

    @abstractmethod
    def iso_args(self) -> List[str]:
        """Return extra genisoimage flags."""
        ...

    def build_iso(
        self, domain_name: str, iso_binary: Path, temp_dir: Path
    ) -> Path:
        """Shared: render files, call genisoimage, return ISO path."""
        cd_dir = temp_dir / "cd_dir"
        cd_dir.mkdir()
        self.render(cd_dir)
        cidata_file = temp_dir / f"{domain_name}-cidata.iso"

        cmd = [
            str(iso_binary),
            "-output",
            cidata_file.name,
            "-volid",
            self.iso_label(),
        ] + self.iso_args() + [str(cd_dir)]

        subprocess.run(
            cmd,
            cwd=str(temp_dir),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return cidata_file


class OpenStackUserData(UserData):
    """OpenStack config-drive format (openstack/latest/)."""

    def iso_label(self) -> str:
        return "config-2"

    def iso_args(self) -> List[str]:
        return [
            "-ldots",
            "-allow-lowercase",
            "-allow-multidot",
            "-l",
            "-publisher",
            "virt-lighting",
            "-quiet",
            "-J",
            "-r",
        ]

    def render(self, output_dir: Path) -> None:
        openstack_dir = output_dir / "openstack" / "latest"
        openstack_dir.mkdir(parents=True)

        # meta_data.json
        meta_data = {
            "availability_zone": "nova",
            "files": [],
            "hostname": self.fqdn or self.hostname,
            "launch_index": 0,
            "local-hostname": self.hostname,
            "name": self.hostname,
            "meta": {},
            "public_keys": {"default": self.ssh_public_key},
            "uuid": self.instance_id,
            "admin_pass": self.root_password,
        }
        (openstack_dir / "meta_data.json").write_text(json.dumps(meta_data))

        # network_data.json
        (openstack_dir / "network_data.json").write_text(
            json.dumps(self._build_network_data())
        )

        # user_data
        (openstack_dir / "user_data").write_text(
            "#cloud-config\n" + yaml.dump(self.cloud_config, Dumper=yaml.Dumper)
        )

    def _build_network_data(self) -> dict:
        """Build OpenStack network_data.json structure."""
        network_data = {
            "links": [],
            "networks": [],
            "services": [{"type": "dns", "address": addr} for addr in self.global_dns],
        }

        for i, iface in enumerate(self.interfaces):
            network_data["links"].append(
                {
                    "id": f"interface{i}",
                    "type": "phy",
                    "ethernet_mac_address": iface.mac,
                }
            )

            if iface.ipv4:
                # Determine if DNS is in the same subnet
                net_dns_nameservers = [
                    dns
                    for dns in iface.dns_nameservers
                    if IPv4Interface(dns) in iface.ipv4.network
                ]
                network_data["networks"].append(
                    {
                        "id": f"private-ipv4-{i}",
                        "type": "ipv4",
                        "link": f"interface{i}",
                        "ip_address": str(iface.ipv4.ip),
                        "netmask": str(iface.ipv4.netmask),
                        "routes": [
                            {
                                "network": "0.0.0.0",
                                "netmask": "0.0.0.0",
                                "gateway": str(iface.gateway.ip),
                            }
                        ],
                        "network_id": self.instance_id,
                        # Workaround for CloudInit: sources.helpers.openstack reads
                        # subnet DNS from dns_nameservers, ignoring the services key
                        "dns_nameservers": net_dns_nameservers,
                        "services": [
                            {"type": "dns", "address": ns}
                            for ns in net_dns_nameservers
                        ],
                    }
                )
            else:
                network_data["networks"].append(
                    {
                        "id": f"private-ipv4-{i}",
                        "type": "ipv4_dhcp",
                        "link": f"interface{i}",
                        "network_id": self.instance_id,
                    }
                )

        return network_data


class CloudInitUserData(UserData, ABC):
    """NoCloud base — shared meta-data + user-data rendering."""

    def iso_label(self) -> str:
        return "cidata"

    def iso_args(self) -> List[str]:
        return ["-joliet", "-R"]

    @abstractmethod
    def _build_network_config(self) -> dict:
        """Version-specific network config schema."""
        ...

    @abstractmethod
    def _build_meta_data(self) -> str:
        """Version-specific meta-data content."""
        ...

    def render(self, output_dir: Path) -> None:
        # user-data (same for all versions)
        (output_dir / "user-data").write_text(
            "#cloud-config\n" + yaml.dump(self.cloud_config, Dumper=yaml.Dumper)
        )

        # meta-data (version-specific)
        (output_dir / "meta-data").write_text(self._build_meta_data())

        # network-config (version-specific)
        (output_dir / "network-config").write_text(
            yaml.dump(self._build_network_config(), Dumper=yaml.Dumper)
        )


class CloudInit22UserData(CloudInitUserData):
    """cloud-init ≤ 22.x — network config v1, legacy ENI meta-data."""

    def _build_network_config(self) -> dict:
        config = []
        for iface in self.interfaces:
            if iface.ipv4:
                subnets = [
                    {
                        "type": "static",
                        "address": str(iface.ipv4),
                        "gateway": str(iface.gateway.ip),
                        "dns_nameservers": iface.dns_nameservers,
                    }
                ]
            else:
                subnets = [{"type": "dhcp"}]
            config.append(
                {
                    "type": "physical",
                    "name": iface.name,
                    "mac_address": iface.mac,
                    "subnets": subnets,
                }
            )
        return {"version": 1, "config": config}

    def _build_meta_data(self) -> str:
        # Legacy ENI-style (replaces META_DATA_ENI template)
        lines = [
            "dsmode: local",
            f"instance-id: iid-{self.hostname}",
            f"local-hostname: {self.hostname}",
        ]
        
        # Add network-interfaces in ENI format if we have a static IP
        if self.interfaces and self.interfaces[0].ipv4:
            iface = self.interfaces[0]
            lines.append("network-interfaces: |")
            lines.append("   iface eth0 inet static")
            lines.append(f"   address {iface.ipv4.ip}")
            lines.append(f"   network {iface.ipv4.network.network_address}")
            lines.append(f"   netmask {iface.ipv4.netmask}")
            lines.append(f"   gateway {iface.gateway.ip}")
        
        return "\n".join(lines) + "\n"


class CloudInit23UserData(CloudInitUserData):
    """cloud-init 23.x+ — network config v2, YAML instance meta-data."""

    def _build_network_config(self) -> dict:
        ethernets = {}
        for iface in self.interfaces:
            eth = {"match": {"macaddress": iface.mac}}
            if iface.ipv4:
                eth["addresses"] = [str(iface.ipv4)]
                eth["routes"] = [
                    {"to": "default", "via": str(iface.gateway.ip)}
                ]
                eth["nameservers"] = {"addresses": iface.dns_nameservers}
            else:
                eth["dhcp4"] = True
            ethernets[iface.name] = eth
        return {"version": 2, "ethernets": ethernets}

    def _build_meta_data(self) -> str:
        meta = {
            "instance-id": self.instance_id,
            "local-hostname": self.hostname,
        }
        return yaml.dump(meta, Dumper=yaml.Dumper)
    
@dataclass
class DomainConfig:
    groups: List[str] = field(default_factory=list)
    memory: int = 1024
    python_interpreter: str = "/usr/bin/python3"
    root_password: str = "root"
    # use a lazy default to avoid requiring an explicit import at top-level
    username: Optional[str] = field(default_factory=lambda: __import__("getpass").getuser())
    vcpus: int = 1
    fqdn: Optional[str] = None
    # match key used in virt_lightning.LibvirtHypervisor.configure_domain
    default_nic_model: str = "virtio"
    bootcmd: List[Any] = field(default_factory=list)
    runcmd: List[Any] = field(default_factory=list)
    meta_data_media_type: str = "cdrom"
    default_bus_type: str = "virtio"
    datasource: str = "openstack"
    cloudinit_version: str = "22"

    def __init__(self, **kwargs):
        # Initialize all fields with their default values first
        cls = self.__class__
        for f in fields(cls):
            if f.default is not MISSING:
                setattr(self, f.name, f.default)
            elif f.default_factory is not MISSING:
                setattr(self, f.name, f.default_factory())
            else:
                # Field has no default, will be set from kwargs or remain unset
                pass

        # Now override with provided kwargs
        field_names = {f.name for f in fields(cls)}
        for name, value in kwargs.items():
            if name in field_names:
                setattr(self, name, value)
            else:
                logger.warning("Unknown field %r passed to %s; ignoring", name, cls.__name__)

    @classmethod
    def from_host(cls, host: dict, configuration) -> "DomainConfig":
        """
        Create a DomainConfig populated from a host dict and Configuration instance,
        applying configuration-level defaults where appropriate.
        """
        return cls(
            groups=host.get("groups") or [],
            memory=host.get("memory"),
            python_interpreter=host.get("python_interpreter"),
            root_password=host.get("root_password", getattr(configuration, "root_password", None)),
            username=host.get("username"),
            vcpus=host.get("vcpus"),
            fqdn=host.get("fqdn"),
            # api.py uses host.get("default_nic_model") to populate key default_nic_mode
            default_nic_model=host.get("default_nic_model"),
            bootcmd=host.get("bootcmd") or [],
            runcmd=host.get("runcmd") or [],
            meta_data_media_type=host.get("meta_data_media_type"),
            default_bus_type=host.get("default_bus_type"),
            datasource=host.get("datasource"),
            cloudinit_version=host.get("cloudinit_version"),
        )

    def merge_with(self, base_config: "DomainConfig") -> "DomainConfig":
        """
        Merge this config with a base config.
        
        Merge strategy:
        - For list fields: use user's list if non-empty, else base list
        - For other fields: use user's value if not None, else base value
        
        This means None is the sentinel for "not set by user, use base value".
        
        Args:
            base_config: The base configuration to merge with
            
        Returns:
            A new DomainConfig with merged values
        """
        merged_kwargs = {}
        
        for f in fields(self.__class__):
            user_value = getattr(self, f.name)
            base_value = getattr(base_config, f.name)
            
            # For list fields: use user value if non-empty, else base value
            if isinstance(user_value, list):
                merged_kwargs[f.name] = user_value if user_value else base_value
            # For other fields: use user value if not None, else base value
            elif user_value is not None:
                merged_kwargs[f.name] = user_value
            else:
                merged_kwargs[f.name] = base_value
        
        return DomainConfig(**merged_kwargs)