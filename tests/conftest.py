import pytest

import libvirt
import virt_lightning.virt_lightning as vl
import pathlib
from unittest.mock import patch
from unittest.mock import Mock

DEFAULT_INI = """
[main]
username=boby
"""



def clean_up():
    conn = libvirt.open("test:///default")
    domainIDs = conn.listDomainsID()
    for domainID in domainIDs:
        dom = conn.lookupByID(domainID)
        if dom.state() != libvirt.VIR_DOMAIN_SHUTOFF:
            dom.destroy()
        dom.undefine()


@pytest.fixture
def hv(scope="function"):
    libvirt_uri = "test:///default"
    hv = vl.LibvirtHypervisor(libvirt_uri)
    hv.conn.getURI = Mock(return_value="qemu:///system")
    yield hv
    clean_up()


@pytest.fixture
def domain(hv, scope="function"):
    yield hv.create_domain(name="a", distro="b")
    clean_up()

@pytest.fixture(autouse=True)
def kvm_binaries(tmp_path):
    kvm_f = tmp_path / "kvm-dummy"
    with kvm_f.open(mode='wt') as fd:
        fd.write("aa")
    vl.KVM_BINARIES = (kvm_f,)


@pytest.fixture
def config_file(tmp_path):
    d = tmp_path / "sub"
    d.mkdir()
    config_file = d / "my_inifile.ini"
    config_file.write_text(DEFAULT_INI)
    return config_file
