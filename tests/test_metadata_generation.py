"""
Tests for cloud-init metadata generation methods.
These tests validate the data structures created for OpenStack and NoCloud formats.
"""
import json
import pytest
import pathlib
import tempfile
import yaml
from unittest.mock import Mock, MagicMock, patch, mock_open, PropertyMock
from ipaddress import IPv4Interface, IPv4Network

import libvirt
import virt_lightning.virt_lightning as vl
from virt_lightning.metadata import DomainConfig


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
    with patch.object(type(hv), 'iso_binary', new_callable=PropertyMock) as mock_iso:
        mock_iso.return_value = pathlib.Path("/usr/bin/genisoimage")
        with patch.object(vl.LibvirtHypervisor, 'get_storage_dir', return_value=pool_dir):
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


class TestGetOpenStackNetworkData:
    """Test get_openstack_network_data method."""
    
    def test_builds_network_data_with_static_ip(self, mock_hv, mock_domain):
        """Test network_data structure with static IP configuration."""
        network_data = mock_hv.get_openstack_network_data(mock_domain)
        
        # Validate structure
        assert "links" in network_data
        assert "networks" in network_data
        assert "services" in network_data
        
        # Validate links
        assert len(network_data["links"]) == 1
        link = network_data["links"][0]
        assert link["id"] == "interface0"
        assert link["type"] == "phy"
        assert link["ethernet_mac_address"] == "52:54:00:12:34:56"
        
        # Validate networks
        assert len(network_data["networks"]) == 1
        network = network_data["networks"][0]
        assert network["id"] == "private-ipv4-0"
        assert network["type"] == "ipv4"
        assert network["link"] == "interface0"
        assert network["ip_address"] == "192.168.122.10"
        assert network["netmask"] == "255.255.255.0"
        assert "routes" in network
        assert network["routes"][0]["gateway"] == "192.168.122.1"
        
        # Validate DNS services
        assert len(network_data["services"]) == 1
        assert network_data["services"][0]["type"] == "dns"
        assert network_data["services"][0]["address"] == "192.168.122.1"
    
    def test_builds_network_data_with_dhcp(self, mock_hv, mock_domain):
        """Test network_data structure with DHCP configuration."""
        # Setup domain with DHCP NIC
        mock_domain.nics = [
            {
                "network": "default",
                "mac": "52:54:00:12:34:56",
                "ipv4": None,  # DHCP
            }
        ]
        
        network_data = mock_hv.get_openstack_network_data(mock_domain)
        
        # Should have link but network uses dhcp
        assert len(network_data["links"]) == 1
        assert len(network_data["networks"]) == 1
        
        network = network_data["networks"][0]
        assert network["id"] == "private-ipv4-0"
        assert network["type"] == "ipv4_dhcp"
    
    def test_builds_network_data_with_multiple_nics(self, mock_hv, mock_domain):
        """Test network_data with multiple network interfaces."""
        mock_domain.nics = [
            {
                "network": "default",
                "mac": "52:54:00:12:34:56",
                "ipv4": IPv4Interface("192.168.122.10/24"),
            },
            {
                "network": "private",
                "mac": "52:54:00:12:34:57",
                "ipv4": IPv4Interface("10.0.0.10/24"),
            },
        ]
        
        # Mock get_network_gateway for both networks
        mock_hv.get_network_gateway = Mock(side_effect=[
            IPv4Interface("192.168.122.1/24"),
            IPv4Interface("10.0.0.1/24"),
        ])
        
        network_data = mock_hv.get_openstack_network_data(mock_domain)
        
        assert len(network_data["links"]) == 2
        assert len(network_data["networks"]) == 2
        
        # Verify both interfaces are configured
        assert network_data["links"][0]["id"] == "interface0"
        assert network_data["links"][1]["id"] == "interface1"
        assert network_data["networks"][0]["ip_address"] == "192.168.122.10"
        assert network_data["networks"][1]["ip_address"] == "10.0.0.10"


class TestPrepareCloudInitOpenStack:
    """Test prepare_cloud_init_openstack_iso method."""
    
    @patch('virt_lightning.virt_lightning.run_cmd')
    def test_creates_openstack_metadata_structure(self, mock_run_cmd, mock_hv, mock_domain):
        """Test that OpenStack metadata has correct structure."""
        # We'll intercept file writes to validate the data
        written_files = {}
        
        original_open = pathlib.Path.open
        
        def mock_path_open(self, mode='r', *args, **kwargs):
            if mode == 'w':
                # Create a mock file that captures writes
                mock_file = MagicMock()
                content = []
                
                def write_side_effect(data):
                    content.append(data)
                
                mock_file.write.side_effect = write_side_effect
                mock_file.__enter__ = Mock(return_value=mock_file)
                mock_file.__exit__ = Mock(return_value=False)
                
                # Store for later validation
                written_files[str(self)] = content
                return mock_file
            elif mode == 'br':
                # Mock binary read for the ISO file
                mock_file = MagicMock()
                mock_file.read.return_value = b'fake iso data'
                mock_file.__enter__ = Mock(return_value=mock_file)
                mock_file.__exit__ = Mock(return_value=False)
                return mock_file
            return original_open(self, mode, *args, **kwargs)
        
        with patch.object(pathlib.Path, 'open', mock_path_open):
            with patch.object(mock_hv, 'create_disk', return_value=Mock()):
                with patch.object(mock_hv.conn, 'newStream', return_value=Mock()):
                    # Mock the directory creation to avoid actual filesystem operations
                    with patch.object(pathlib.Path, 'mkdir'):
                        mock_hv.prepare_cloud_init_openstack_iso(mock_domain)
        
        # Find and validate meta_data.json
        meta_data_files = [k for k in written_files.keys() if 'meta_data.json' in k]
        assert len(meta_data_files) == 1, "Should create meta_data.json"
        
        meta_data_content = ''.join(written_files[meta_data_files[0]])
        meta_data = json.loads(meta_data_content)
        
        # Validate meta_data structure
        assert meta_data["hostname"] == "testvm.example.com"
        assert meta_data["name"] == "testvm"
        assert meta_data["local-hostname"] == "testvm"
        assert meta_data["uuid"] == "12345678-1234-1234-1234-123456789abc"
        assert meta_data["admin_pass"] == "testpass"
        assert meta_data["availability_zone"] == "nova"
        assert "public_keys" in meta_data
        assert meta_data["public_keys"]["default"] == "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDtest"
    
    @patch('virt_lightning.virt_lightning.run_cmd')
    def test_creates_user_data_file(self, mock_run_cmd, mock_hv, mock_domain):
        """Test that user_data file is created with correct cloud-config."""
        written_files = {}
        original_open = pathlib.Path.open
        
        def capture_writes(path_obj, mode='r', *args, **kwargs):
            if mode == 'w':
                mock_file = MagicMock()
                content = []
                mock_file.write.side_effect = lambda data: content.append(data)
                mock_file.__enter__ = Mock(return_value=mock_file)
                mock_file.__exit__ = Mock(return_value=False)
                written_files[str(path_obj)] = content
                return mock_file
            elif mode == 'br':
                # Mock binary read for the ISO file
                mock_file = MagicMock()
                mock_file.read.return_value = b'fake iso data'
                mock_file.__enter__ = Mock(return_value=mock_file)
                mock_file.__exit__ = Mock(return_value=False)
                return mock_file
            return original_open(path_obj, mode, *args, **kwargs)
        
        with patch.object(pathlib.Path, 'open', capture_writes):
            with patch.object(mock_hv, 'create_disk', return_value=Mock()):
                with patch.object(mock_hv.conn, 'newStream', return_value=Mock()):
                    with patch.object(pathlib.Path, 'mkdir'):
                        mock_hv.prepare_cloud_init_openstack_iso(mock_domain)
        
        # Find user_data file
        user_data_files = [k for k in written_files.keys() if 'user_data' in k and 'meta_data' not in k]
        assert len(user_data_files) == 1
        
        user_data_content = ''.join(written_files[user_data_files[0]])
        
        # Should start with cloud-config header
        assert user_data_content.startswith("#cloud-config\n")
        
        # Parse YAML content
        yaml_content = user_data_content[len("#cloud-config\n"):]
        user_data = yaml.safe_load(yaml_content)
        
        # Validate user_data contains expected fields
        assert user_data["resize_rootfs"] is True
        assert user_data["disable_root"] is False
        assert user_data["password"] == "testpass"
        assert "bootcmd" in user_data
        assert "runcmd" in user_data


class TestPrepareCloudInitNoCloud:
    """Test prepare_cloud_init_nocloud_iso method."""
    
    @patch('virt_lightning.virt_lightning.run_cmd')
    def test_creates_nocloud_files(self, mock_run_cmd, mock_hv, mock_domain):
        """Test that NoCloud format creates user-data, meta-data, and network-config."""
        written_files = {}
        
        def capture_writes(path_obj, mode='r', *args, **kwargs):
            if mode == 'w':
                mock_file = MagicMock()
                content = []
                mock_file.write.side_effect = lambda data: content.append(data)
                mock_file.__enter__ = Mock(return_value=mock_file)
                mock_file.__exit__ = Mock(return_value=False)
                written_files[str(path_obj)] = content
                return mock_file
            # Default behavior for read mode
            return MagicMock()
        
        with patch.object(pathlib.Path, 'open', capture_writes):
            with patch.object(mock_hv, 'create_disk', return_value=Mock()):
                with patch.object(mock_hv.conn, 'newStream', return_value=Mock()):
                    with patch.object(pathlib.Path, 'mkdir'):
                        with patch.object(mock_hv, 'get_network_gateway', return_value=IPv4Interface("192.168.122.1/24")):
                            mock_hv.prepare_cloud_init_nocloud_iso(mock_domain)
        
        # Verify all three required files are created
        file_names = [pathlib.Path(k).name for k in written_files.keys()]
        assert "user-data" in file_names
        assert "meta-data" in file_names
        assert "network-config" in file_names
    
    @patch('virt_lightning.virt_lightning.run_cmd')
    def test_network_config_structure(self, mock_run_cmd, mock_hv, mock_domain):
        """Test NoCloud network-config has correct structure."""
        written_files = {}
        
        def capture_writes(path_obj, mode='r', *args, **kwargs):
            if mode == 'w':
                mock_file = MagicMock()
                content = []
                mock_file.write.side_effect = lambda data: content.append(data)
                mock_file.__enter__ = Mock(return_value=mock_file)
                mock_file.__exit__ = Mock(return_value=False)
                written_files[str(path_obj)] = content
                return mock_file
            return MagicMock()
        
        with patch.object(pathlib.Path, 'open', capture_writes):
            with patch.object(mock_hv, 'create_disk', return_value=Mock()):
                with patch.object(mock_hv.conn, 'newStream', return_value=Mock()):
                    with patch.object(pathlib.Path, 'mkdir'):
                        with patch.object(mock_hv, 'get_network_gateway', return_value=IPv4Interface("192.168.122.1/24")):
                            mock_hv.prepare_cloud_init_nocloud_iso(mock_domain)
        
        # Find network-config file
        network_config_files = [k for k in written_files.keys() if 'network-config' in k]
        assert len(network_config_files) == 1
        
        network_config_content = ''.join(written_files[network_config_files[0]])
        network_config = yaml.safe_load(network_config_content)
        
        # Validate structure
        assert network_config["version"] == 1
        assert "config" in network_config
        assert len(network_config["config"]) == 1
        
        # Validate NIC configuration
        nic_config = network_config["config"][0]
        assert nic_config["type"] == "physical"
        assert nic_config["name"] == "eth0"
        assert nic_config["mac_address"] == "52:54:00:12:34:56"
        
        # Validate subnet configuration
        assert "subnets" in nic_config
        subnet = nic_config["subnets"][0]
        assert subnet["type"] == "static"
        assert subnet["address"] == "192.168.122.10/24"
        assert subnet["gateway"] == "192.168.122.1"
    
    @patch('virt_lightning.virt_lightning.run_cmd')
    def test_dhcp_network_config(self, mock_run_cmd, mock_hv, mock_domain):
        """Test NoCloud network-config with DHCP."""
        # Setup DHCP NIC
        mock_domain.nics = [
            {
                "network": "default",
                "mac": "52:54:00:12:34:56",
                "ipv4": None,  # DHCP
            }
        ]
        
        written_files = {}
        
        def capture_writes(path_obj, mode='r', *args, **kwargs):
            if mode == 'w':
                mock_file = MagicMock()
                content = []
                mock_file.write.side_effect = lambda data: content.append(data)
                mock_file.__enter__ = Mock(return_value=mock_file)
                mock_file.__exit__ = Mock(return_value=False)
                written_files[str(path_obj)] = content
                return mock_file
            return MagicMock()
        
        with patch.object(pathlib.Path, 'open', capture_writes):
            with patch.object(mock_hv, 'create_disk', return_value=Mock()):
                with patch.object(mock_hv.conn, 'newStream', return_value=Mock()):
                    with patch.object(pathlib.Path, 'mkdir'):
                        with patch.object(mock_hv, 'get_network_gateway', return_value=IPv4Interface("192.168.122.1/24")):
                            mock_hv.prepare_cloud_init_nocloud_iso(mock_domain)
        
        # Find and parse network-config
        network_config_files = [k for k in written_files.keys() if 'network-config' in k]
        network_config_content = ''.join(written_files[network_config_files[0]])
        network_config = yaml.safe_load(network_config_content)
        
        # Verify DHCP configuration
        nic_config = network_config["config"][0]
        subnet = nic_config["subnets"][0]
        assert subnet["type"] == "dhcp"


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
        
        with patch.object(vl.LibvirtHypervisor, 'get_storage_dir', return_value=pool_dir):
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
        
        with patch.object(vl.LibvirtHypervisor, 'get_storage_dir', return_value=pool_dir):
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
        
        with patch.object(vl.LibvirtHypervisor, 'get_storage_dir', return_value=pool_dir):
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
        
        with patch.object(vl.LibvirtHypervisor, 'get_storage_dir', return_value=pool_dir):
            config = hv.get_distro_configuration("empty")
        
        # Should return default DomainConfig
        assert isinstance(config, DomainConfig)
        assert config.memory == 1024
