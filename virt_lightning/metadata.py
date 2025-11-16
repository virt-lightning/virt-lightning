from dataclasses import dataclass, field, asdict
from typing import Optional, List, Any
from dataclasses import fields, MISSING
import logging

logger = logging.getLogger(__name__)

class Userdata:
    """
    Class to represent user data for a virtual machine.
    This class is used to store and manage user data that can be passed to the VM.
    """

    def __init__(self, **kwargs):
        """
        Initialize the Userdata instance with the provided userdata string.

        :param userdata: The user data string to be stored.
        """
        self.resize_rootfs = True
        self.disable_root = 0
        self.bootcmd = []
        self.runcmd = []

    def __str__(self):
        """
        Return the string representation of the Userdata instance.

        :return: The user data string.
        """
        attrs = vars(self)
        return "\n".join(f"{k}: {v}" for k, v in attrs.items())
    
@dataclass
class DomainConfig:
    groups: List[str] = field(default_factory=list)
    memory: int = 1024
    python_interpreter: str = "/usr/bin/python3"
    root_password: str = "root"
    ssh_key_file: Optional[str] = None
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

    def __init__(self, **kwargs):

        cls = self.__class__
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
            ssh_key_file=host.get("ssh_key_file", getattr(configuration, "ssh_key_file", None)),
            username=host.get("username"),
            vcpus=host.get("vcpus"),
            fqdn=host.get("fqdn"),
            # api.py uses host.get("default_nic_model") to populate key default_nic_mode
            default_nic_model=host.get("default_nic_model"),
            bootcmd=host.get("bootcmd") or [],
            runcmd=host.get("runcmd") or [],
            meta_data_media_type=host.get("meta_data_media_type"),
            default_bus_type=host.get("default_bus_type"),
        )