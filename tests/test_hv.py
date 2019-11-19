import virt_lightning

import ipaddress
import libvirt
import pathlib
from unittest.mock import call
from unittest.mock import Mock
from unittest.mock import patch


def test_arch(hv):
    assert hv.arch == "i686"


def test_domain_type(hv):
    assert hv.domain_type == "test"


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
    assert isinstance(disk, libvirt.virStorageVol)


def test_get_free_ipv4(hv):
    ipv4_1 = hv.get_free_ipv4()
    ipv4_2 = hv.get_free_ipv4()

    assert str(ipv4_1.ip) == "1.0.0.5"
    assert str(ipv4_2) == "1.0.0.6/24"


def test_create_disk_with_options(hv):
    disk = hv.create_disk("foo_all", size=3, backing_on=True)
    assert isinstance(disk, libvirt.virStorageVol)


def test_remove_domain_from_network(hv, domain):
    NET_XML = """<network>
    <name>default</name>
    <uuid>911f54a7-fb02-41ed-9ca1-b35cdc2e6e05</uuid>
    <forward mode='nat'>
        <nat>
        <port start='1024' end='65535'/>
        </nat>
    </forward>
    <bridge name='virt-lightning' stp='off' delay='0'/>
    <mac address='52:54:00:cc:7e:d1'/>
    <dns>
        <host ip='192.168.123.5'>
        <hostname>a</hostname>
        </host>
    </dns>
    <ip address='192.168.123.1' netmask='255.255.255.0'>
        <dhcp>
        <host mac='52:54:00:0f:91:5e' ip='192.168.123.5'/>
        <host mac='52:54:00:0f:91:33' ip='192.168.123.7'/>
        </dhcp>
    </ip>
    </network>"""
    mock_mac_addresses = patch("LibvirtDomain.mac_adresses")
    mock_mac_addresses.__get__ = Mock(
        return_value=["52:54:00:0f:91:5e", "52:54:00:0f:91:33"]
    )
    domain.ipv4 = "192.168.123.5/24"
    hv.network_obj.XMLDesc = Mock(return_value=NET_XML)
    hv.network_obj.update = Mock()
    hv.remove_domain_from_network(domain)
    hv.network_obj.update.call_count == 3