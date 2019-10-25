import pytest

import libvirt
import virt_lightning.virt_lightning as vl
import pathlib
from unittest.mock import patch
from unittest.mock import Mock

DEFAULT_INI = """
[main]
root_password=boby
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
    conn = libvirt.open("test:///default")
    conn.getURI = Mock(return_value="qemu:///system")
    hv = vl.LibvirtHypervisor(conn)
    with patch.object(pathlib.Path, 'exists') as mock_exists:
        mock_exists.return_value = False
        hv.init_storage_pool("foo_bar")
    hv.init_network("my_network", "1.0.0.0/24")
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

@pytest.fixture(autouse=True)
def qemu_dir(tmp_path):
    qemu_dir = tmp_path / "kvm-dummy"
    if not qemu_dir.exists():
        qemu_dir.mkdir()
    vl.QEMU_DIR = str(qemu_dir)

@pytest.fixture(autouse=True)
def storage_dir(tmp_path):
    pool_dir = tmp_path / "pool"
    upstream_dir = pool_dir / "upstream"
    if not pool_dir.exists():
        pool_dir.mkdir()
    if not upstream_dir.exists():
        upstream_dir.mkdir()
    vl.DEFAULT_STORAGE_DIR = str(pool_dir)

@pytest.fixture
def config_file(tmp_path):
    d = tmp_path / "sub"
    d.mkdir()
    config_file = d / "my_inifile.ini"
    config_file.write_text(DEFAULT_INI)
    return config_file
