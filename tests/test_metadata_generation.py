"""
Tests for cloud-init metadata generation methods.
These tests validate the new UserData-based lifecycle: _create_userdata() dispatch,
start() with DomainConfig, and distro configuration loading.
"""
import pathlib
from ipaddress import IPv4Interface, IPv4Network
from unittest.mock import Mock, PropertyMock, patch

import libvirt
import pytest

import virt_lightning.virt_lightning as vl
from virt_lightning.metadata import (
    CloudInit22UserData,
    CloudInit23UserData,
    DomainConfig,
    OpenStackUserData,
)


@pytest.fixture
def pool_dirs(tmp_path):
    """Create pool directory structure for tests."""
    pool_dir = tmp_path / "pool"
    upstream_dir = pool_dir / "upstream"
    upstream_dir.mkdir(parents=True, exist_ok=True)
    return pool_dir, upstream_dir


@pytest.fixture
def mock_hv(pool_dirs):
    """Create a mock hypervisor with basic setup."""
    pool_dir, upstream_dir = pool_dirs

    conn = Mock()
    conn.getURI = Mock(return_value="qemu:///system")

    hv = vl.LibvirtHypervisor(conn)

    hv.storage_pool_obj = Mock()
    hv.storage_pool_obj.storageVolLookupByName = Mock(side_effect=libvirt.libvirtError("Not found"))

    # Setup network
    hv.network = IPv4Network("192.168.122.0/24")
    hv.gateway = IPv4Interface("192.168.122.1/24")
    hv.dns = IPv4Interface("192.168.122.1/24")
    hv.network_obj = Mock()

    # Mock get_network_gateway to return the gateway by default
    hv.get_network_gateway = Mock(return_value=IPv4Interface("192.168.122.1/24"))

    # Mock the iso_binary property using PropertyMock
    with patch.object(type(hv), "iso_binary", new_callable=PropertyMock) as mock_iso:
        mock_iso.return_value = pathlib.Path("/usr/bin/genisoimage")
        with patch.object(vl.LibvirtHypervisor, "get_storage_dir", return_value=pool_dir):
            yield hv


@pytest.fixture
def mock_domain():
    """Create a mock LibvirtDomain with test data."""
    dom_obj = Mock()
    dom_obj.name.return_value = "testvm"
    dom_obj.UUIDString.return_value = "12345678-1234-1234-1234-123456789abc"

    # Mock metadata storage
    metadata_store = {}

    def mock_set_metadata(meta_type, meta, namespace, uri, flags):
        metadata_store[uri] = meta

    def mock_get_metadata(meta_type, uri):
        if uri in metadata_store:
            return metadata_store[uri]
        err = libvirt.libvirtError("No metadata")
        err.get_error_code = lambda: libvirt.VIR_ERR_NO_DOMAIN_METADATA
        raise err

    dom_obj.setMetadata.side_effect = mock_set_metadata
    dom_obj.metadata.side_effect = mock_get_metadata

    domain = vl.LibvirtDomain(dom_obj)
    domain.name = "testvm"
    domain.fqdn = "testvm.example.com"
    domain.ssh_key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDtest"
    domain.root_password = "testpass"
    domain.username = "testuser"
    domain.ipv4 = IPv4Interface("192.168.122.10/24")

    # Setup user_data
    domain.user_data = {
        "resize_rootfs": True,
        "disable_root": False,
        "password": "testpass",
        "chpasswd": {"expire": False},
        "ssh_pwauth": True,
        "ssh_authorized_keys": ["ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDtest"],
        "bootcmd": ["echo 'boot'"],
        "runcmd": ["echo 'run'"],
    }

    # Setup NICs
    domain.nics = [
        {
            "network": "default",
            "mac": "52:54:00:12:34:56",
            "ipv4": IPv4Interface("192.168.122.10/24"),
        }
    ]

    return domain


class TestCreateUserData:
    """Test _create_userdata() returns correct class for each config."""

    def test_default_config_returns_cloudinit23(self, mock_hv, mock_domain):
        config = DomainConfig()
        userdata = mock_hv._create_userdata(mock_domain, config)
        assert isinstance(userdata, CloudInit23UserData)

    def test_openstack_datasource_returns_openstack(self, mock_hv, mock_domain):
        config = DomainConfig(datasource="openstack")
        userdata = mock_hv._create_userdata(mock_domain, config)
        assert isinstance(userdata, OpenStackUserData)

    def test_nocloud_returns_cloudinit23_by_default(self, mock_hv, mock_domain):
        config = DomainConfig(datasource="nocloud")
        userdata = mock_hv._create_userdata(mock_domain, config)
        assert isinstance(userdata, CloudInit23UserData)

    def test_nocloud_version_22_returns_cloudinit22(self, mock_hv, mock_domain):
        config = DomainConfig(datasource="nocloud", cloudinit_version="22")
        userdata = mock_hv._create_userdata(mock_domain, config)
        assert isinstance(userdata, CloudInit22UserData)

    def test_nocloud_version_23_returns_cloudinit23(self, mock_hv, mock_domain):
        config = DomainConfig(datasource="nocloud", cloudinit_version="23")
        userdata = mock_hv._create_userdata(mock_domain, config)
        assert isinstance(userdata, CloudInit23UserData)

    def test_nocloud_version_24_returns_cloudinit23(self, mock_hv, mock_domain):
        config = DomainConfig(datasource="nocloud", cloudinit_version="24")
        userdata = mock_hv._create_userdata(mock_domain, config)
        assert isinstance(userdata, CloudInit23UserData)


class TestStart:
    """Test start() uses new UserData-based flow."""

    @patch("subprocess.run")
    def test_start_calls_build_iso_and_uploads(self, mock_subprocess_run, mock_hv, mock_domain):
        config = DomainConfig()

        def fake_genisoimage(cmd, **kwargs):
            cwd = kwargs.get("cwd", ".")
            idx = cmd.index("-output")
            (pathlib.Path(cwd) / cmd[idx + 1]).write_bytes(b"fake iso")
        mock_subprocess_run.side_effect = fake_genisoimage

        mock_volume = Mock()
        mock_volume.path.return_value = "/fake/testvm-cidata.iso"
        mock_hv.create_disk = Mock(return_value=mock_volume)
        mock_stream = Mock()
        mock_hv.conn.newStream = Mock(return_value=mock_stream)
        mock_domain.meta_data_media_type = "cdrom"
        mock_domain.dom.create = Mock()
        mock_hv.remove_domain_from_network = Mock()
        mock_hv.add_domain_to_network = Mock()

        mock_hv.start(mock_domain, config)

        mock_hv.create_disk.assert_called_once()
        mock_volume.upload.assert_called_once()
        mock_stream.send.assert_called_once()
        mock_stream.finish.assert_called_once()
        mock_domain.dom.create.assert_called_once()
        mock_hv.remove_domain_from_network.assert_called_once_with(mock_domain)
        mock_hv.add_domain_to_network.assert_called_once_with(mock_domain)

    @patch("subprocess.run")
    def test_start_nocloud_uses_cloudinit22(self, mock_subprocess_run, mock_hv, mock_domain):
        config = DomainConfig(datasource="nocloud", cloudinit_version="22")

        def fake_genisoimage(cmd, **kwargs):
            cwd = kwargs.get("cwd", ".")
            idx = cmd.index("-output")
            (pathlib.Path(cwd) / cmd[idx + 1]).write_bytes(b"fake iso")
        mock_subprocess_run.side_effect = fake_genisoimage

        mock_volume = Mock()
        mock_volume.path.return_value = "/fake/testvm-cidata.iso"
        mock_hv.create_disk = Mock(return_value=mock_volume)
        mock_hv.conn.newStream = Mock(return_value=Mock())
        mock_domain.meta_data_media_type = "cdrom"
        mock_domain.dom.create = Mock()
        mock_hv.remove_domain_from_network = Mock()
        mock_hv.add_domain_to_network = Mock()

        mock_hv.start(mock_domain, config)

        # Verify genisoimage was called with cidata label (nocloud)
        call_args = mock_subprocess_run.call_args[0][0]
        assert "-volid" in call_args
        volid_idx = call_args.index("-volid")
        assert call_args[volid_idx + 1] == "cidata"


class TestConfigureDomainReturnsConfig:
    """Test configure_domain returns the merged config."""

    def test_returns_merged_config(self, pool_dirs):
        pool_dir, upstream_dir = pool_dirs

        distro_config_file = upstream_dir / "test-distro.yaml"
        distro_config_file.write_text("memory: 2048\ndatasource: nocloud\n")

        conn = Mock()
        hv = vl.LibvirtHypervisor(conn)

        domain = Mock()
        domain.distro = "test-distro"

        user_config = DomainConfig(vcpus=4, memory=None, datasource=None)

        with patch.object(vl.LibvirtHypervisor, "get_storage_dir", return_value=pool_dir):
            config = hv.configure_domain(domain, user_config)

        assert isinstance(config, DomainConfig)
        assert config.memory == 2048
        assert config.vcpus == 4
        assert config.datasource == "nocloud"


class TestGetDistroConfiguration:
    """Test get_distro_configuration method."""

    def test_loads_distro_config_from_yaml(self, pool_dirs):
        """Test loading distro-specific configuration from YAML."""
        pool_dir, upstream_dir = pool_dirs

        distro_config_file = upstream_dir / "centos-8.yaml"
        distro_config_file.write_text("""
memory: 2048
vcpus: 2
username: centos
root_password: centos123
python_interpreter: /usr/bin/python3
default_nic_model: virtio
""")

        conn = Mock()
        hv = vl.LibvirtHypervisor(conn)

        with patch.object(vl.LibvirtHypervisor, "get_storage_dir", return_value=pool_dir):
            config = hv.get_distro_configuration("centos-8")

        # Validate loaded configuration
        assert isinstance(config, DomainConfig)
        assert config.memory == 2048
        assert config.vcpus == 2
        assert config.username == "centos"
        assert config.root_password == "centos123"
        assert config.python_interpreter == "/usr/bin/python3"
        assert config.default_nic_model == "virtio"

    def test_returns_default_config_if_file_not_found(self, pool_dirs):
        """Test returns default DomainConfig if distro file doesn't exist."""
        pool_dir, upstream_dir = pool_dirs

        conn = Mock()
        hv = vl.LibvirtHypervisor(conn)

        with patch.object(vl.LibvirtHypervisor, "get_storage_dir", return_value=pool_dir):
            config = hv.get_distro_configuration("nonexistent-distro")

        # Should return default DomainConfig
        assert isinstance(config, DomainConfig)
        assert config.memory == 1024  # Default value
        assert config.vcpus == 1  # Default value

    def test_handles_partial_config(self, pool_dirs):
        """Test loading config with only some fields specified."""
        pool_dir, upstream_dir = pool_dirs

        distro_config_file = upstream_dir / "minimal.yaml"
        distro_config_file.write_text("""
memory: 4096
username: admin
""")

        conn = Mock()
        hv = vl.LibvirtHypervisor(conn)

        with patch.object(vl.LibvirtHypervisor, "get_storage_dir", return_value=pool_dir):
            config = hv.get_distro_configuration("minimal")

        # Should have specified values
        assert config.memory == 4096
        assert config.username == "admin"

        # Should have defaults for unspecified values
        assert config.vcpus == 1
        assert config.python_interpreter == "/usr/bin/python3"

    def test_handles_empty_yaml_file(self, pool_dirs):
        """Test loading an empty YAML file."""
        pool_dir, upstream_dir = pool_dirs

        distro_config_file = upstream_dir / "empty.yaml"
        distro_config_file.write_text("")

        conn = Mock()
        hv = vl.LibvirtHypervisor(conn)

        with patch.object(vl.LibvirtHypervisor, "get_storage_dir", return_value=pool_dir):
            config = hv.get_distro_configuration("empty")

        # Should return default DomainConfig
        assert isinstance(config, DomainConfig)
        assert config.memory == 1024
