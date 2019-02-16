import virt_lightning

import pathlib
from unittest.mock import patch


def test_arch():
    hv = virt_lightning.LibvirtHypervisor("test:///default")
    assert hv.arch == 'i686'


def test_domain_type():
    hv = virt_lightning.LibvirtHypervisor("test:///default")
    assert hv.domain_type == 'test'


def test_kvm_binary():
    def mock_exists(path):
        if path == pathlib.PosixPath("/usr/bin/kvm"):
            return True
    hv = virt_lightning.LibvirtHypervisor("test:///default")
    with patch.object(pathlib.Path, 'exists', mock_exists):
        assert hv.kvm_binary == pathlib.PosixPath("/usr/bin/kvm")


def test_init_storage_pool():
    hv = virt_lightning.LibvirtHypervisor("test:///default")
    with patch.object(pathlib.Path, 'exists') as mock_exists:
        mock_exists.return_value = False
        hv.init_storage_pool("foo_bar")
    assert hv.conn.storagePoolLookupByName("foo_bar")


def test_create_domain():
    hv = virt_lightning.LibvirtHypervisor("test:///default")
    domain = hv.create_domain(name="a", distro="b")
    print(domain.name)
    assert domain.name() == "a"
    assert domain.distro == "b"
