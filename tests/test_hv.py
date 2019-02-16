import virt_lightning

import pathlib
from unittest.mock import patch


def test_arch(hv):
    assert hv.arch == 'i686'


def test_domain_type(hv):
    assert hv.domain_type == 'test'


def test_kvm_binary(hv):
    assert hv.kvm_binary.name == "kvm-dummy"


def test_init_storage_pool(hv):
    with patch.object(pathlib.Path, 'exists') as mock_exists:
        mock_exists.return_value = False
        hv.init_storage_pool("foo_bar")
    assert hv.conn.storagePoolLookupByName("foo_bar")


def test_create_domain(hv):
    domain = hv.create_domain(name="a", distro="b")
    assert domain

def test_distro_available(hv, tmpdir):
    hv.storage_pool_obj = hv.create_storage_pool("foo", tmpdir)
    assert hv.distro_available() == []
    upstream_d = tmpdir / "upstream"
    upstream_d.mkdir()
    distro_1 = upstream_d / "distro_1.qcow2"
    distro_1.write(b"a")
    assert hv.distro_available() == ["distro_1"]
