import configparser
from abc import ABCMeta, abstractproperty
from pathlib import PosixPath

DEFAULT_CONFIGFILE = PosixPath("~/.config/virt-lightning/config.ini")


DEFAULT_CONFIGURATION = {
    "main": {
        "libvirt_uri": "qemu:///system",
        "root_password": "root",
        "storage_pool": "virt-lightning",
        "network_name": "virt-lightning",
        "network_cidr": "192.168.123.0/24",
        "network_auto_clean_up": True,
        "ssh_key_file": "~/.ssh/id_rsa.pub",
    }
}


class AbstractConfiguration(metaclass=ABCMeta):
    @abstractproperty
    def libvirt_uri(self):
        pass

    @abstractproperty
    def network_name(self):
        pass

    @abstractproperty
    def network_cidr(self):
        pass

    @abstractproperty
    def network_auto_clean_up(self):
        pass

    @abstractproperty
    def root_password(self):
        pass

    @abstractproperty
    def ssh_key_file(self):
        pass

    @abstractproperty
    def storage_pool(self):
        pass

    def __repr__(self):
        return "Configuration(libvirt_uri={uri}, username={username})".format(
            uri=self.libvirt_uri, username=self.username
        )


class Configuration(AbstractConfiguration):
    def __init__(self):
        self.data = configparser.ConfigParser()
        self.data["main"] = DEFAULT_CONFIGURATION["main"]
        if DEFAULT_CONFIGFILE.expanduser().exists():
            self.load_file(DEFAULT_CONFIGFILE.expanduser())

    def __get(self, key):
        return self.data.get("main", key)

    @property
    def libvirt_uri(self):
        return self.__get("libvirt_uri")

    @property
    def network_name(self):
        return self.__get("network_name")

    @property
    def network_cidr(self):
        return self.__get("network_cidr")

    @property
    def network_auto_clean_up(self):
        return self.__get("network_auto_clean_up")

    @property
    def root_password(self):
        return self.__get("root_password")

    @property
    def ssh_key_file(self):
        return self.__get("ssh_key_file")

    @property
    def storage_pool(self):
        return self.__get("storage_pool")

    def load_file(self, config_file):
        self.data.read_string(config_file.read_text())
