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


def test_get_storage_dir(hv):
    assert hv.get_storage_dir().name == "pool"


def test_create_disk(hv):
    disk = hv.create_disk("foo")
    assert disk.name() == "foo.qcow2"
    assert disk.path().endswith("/pool/foo.qcow2")


def test_get_free_ipv4(hv):
    ipv4_1 = hv.get_free_ipv4()
    ipv4_2 = hv.get_free_ipv4()

    assert str(ipv4_1.ip) == "1.0.0.5"
    assert str(ipv4_2) == "1.0.0.6/24"
