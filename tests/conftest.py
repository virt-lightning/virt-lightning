import pytest

import libvirt
import virt_lightning
import pathlib
from unittest.mock import patch
from unittest.mock import Mock

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
    hv = virt_lightning.LibvirtHypervisor(libvirt_uri)
    hv.conn.getURI = Mock(return_value="qemu:///session")
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
    virt_lightning.KVM_BINARIES = (kvm_f,)
