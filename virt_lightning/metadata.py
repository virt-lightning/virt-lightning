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