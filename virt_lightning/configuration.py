import configparser
import getpass
import os
from abc import ABCMeta, abstractproperty

DEFAULT_CONFIGFILE = "{home}/.config/virt-lightning/config.ini".format(
    home=os.environ["HOME"]
)

DEFAULT_CONFIGURATION = {
    "main": {
        "libvirt_uri": "qemu:///system" if os.geteuid() == 0 else "qemu:///session",
        "bridge": "virbr0",
        "username": getpass.getuser(),
        "root_password": "root",
        "storage_pool": "virt-lightning",
        "ssh_key_file": "~/.ssh/id_rsa.pub",
    }
}


class AbstractConfiguration(metaclass=ABCMeta):
    @abstractproperty
    def libvirt_uri(self):
        pass

    @abstractproperty
    def username(self):
        pass

    @abstractproperty
    def bridge(self):
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
    def __init__(self, obj):
        self.data = obj

    def __get(self, key):
        return self.data.get("main", key)

    @property
    def libvirt_uri(self):
        if self.__get("libvirt_uri"):
            return self.__get("libvirt_uri")
        if os.geteuid() == 0:
            return "qemu:///system"
        else:
            return "quemu:///session"

    @property
    def username(self):
        return self.__get("username")

    @property
    def bridge(self):
        return self.__get("bridge")

    @property
    def root_password(self):
        return self.__get("root_password")

    @property
    def ssh_key_file(self):
        return self.__get("ssh_key_file")

    @property
    def storage_pool(self):
        return self.__get("storage_pool")


class ReadConfigShell:
    def __init__(self, filename=None):
        self.filename = filename
        self.data = None

    def __readfile(self):
        if self.filename == DEFAULT_CONFIGFILE and not os.path.isfile(
            DEFAULT_CONFIGFILE
        ):
            self.filename = None
        else:
            with open(self.filename, "r", encoding="utf-8") as f:
                self.data = f.read()

    def load(self):
        parsed = configparser.ConfigParser()

        self.__readfile()

        if not self.filename:
            parsed.read_dict(DEFAULT_CONFIGURATION)
            config = Configuration(parsed)

            return config

        parsed.read_string(self.data)
        config = Configuration(parsed)

        return config

    def __repr__(self):
        return "Config(filename={filename})".format(filename=self.filename)
