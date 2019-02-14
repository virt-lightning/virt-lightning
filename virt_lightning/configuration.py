from abc import ABCMeta, abstractproperty
import configparser
import os
import getpass

DEFAULT_CONFIGURATION = {
    'settings': {
        "libvirt_uri": "qemu:///system" if os.geteuid() == 0 else "qemu:///session",
        "network": "192.168.122.0/24",
        "gateway": "192.168.122.1/24",
        "bridge": "virbr0",
        "username": getpass.getuser(),
        "root_password": "root",
        "storage_pool": "default",
        "ssh_key_file": "~/.ssh/id_rsa.pub",
    },
}

class AbstractConfiguration(metaclass=ABCMeta):
    @abstractproperty
    def libvirt_uri(self):
        pass

    @abstractproperty
    def username(self):
        pass

    @abstractproperty
    def network(self):
        pass

    @abstractproperty
    def gateway(self):
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
                    uri=self.libvirt_uri, username=self.username,
                )

class Configuration(AbstractConfiguration):
    def __init__(self, obj):
        self.data = obj

    def __get(self, key):
        return self.data.get("settings", key)

    @property
    def libvirt_uri(self):
        try:
            return self.__get("libvirt_uri")
        except:
            pass

        if os.geteuid() == 0:
            path = "system"
        else:
            path = "session"

        return "qemu:///{path}".format(path=path)

    @property
    def username(self):
        try:
            return self.__get("username")
        except:
            return getpass.getuser()

    @property
    def network(self):
        return self.__get("network") 

    @property
    def gateway(self):
        return self.__get("gateway") 

    @property
    def bridge(self):
        return self.__get("bridge") 

    @property
    def root_password(self):
        try:
            return self.__get("root_password") 
        except:
            return None

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
        with open(self.filename, "r", encoding="utf-8") as f:
            self.data = f.read()

    def load(self):
        parsed = configparser.ConfigParser()

        if not self.filename:
            parsed.read_dict(DEFAULT_CONFIGURATION)
            config = Configuration(parsed)

            return config

        self.__readfile()

        parsed.read_string(self.data)
        config = Configuration(parsed)

        return config
    
    def __repr__(self):
        return "Config(filename={filename})".format(
                    filename=self.filename,
                )
