"""
Tests for the UserData class hierarchy.
Validates rendering, ISO creation, and data format for all UserData subclasses.
"""
import json
import pytest
import tempfile
from pathlib import Path
from ipaddress import IPv4Interface
from unittest.mock import Mock, MagicMock, patch
import yaml

from virt_lightning.metadata import (
    NetworkInterface,
    UserData,
    OpenStackUserData,
    CloudInitUserData,
    CloudInit22UserData,
    CloudInit23UserData,
)


@pytest.fixture
def sample_interfaces():
    """Create sample NetworkInterface list for testing."""
    return [
        NetworkInterface(
            name="eth0",
            mac="52:54:00:12:34:56",
            ipv4=IPv4Interface("192.168.122.10/24"),
            gateway=IPv4Interface("192.168.122.1/24"),
            dns_nameservers=["192.168.122.1"],
        ),
        NetworkInterface(
            name="eth1",
            mac="52:54:00:12:34:57",
            ipv4=None,  # DHCP
            gateway=IPv4Interface("10.0.0.1/24"),
            dns_nameservers=["10.0.0.1"],
        ),
    ]


@pytest.fixture
def sample_cloud_config():
    """Create sample cloud-config dict."""
    return {
        "resize_rootfs": True,
        "disable_root": False,
        "password": "testpass",
        "chpasswd": {"list": "root:testpass\n", "expire": False},
        "ssh_pwauth": True,
        "ssh_authorized_keys": ["ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDtest"],
        "bootcmd": ["echo 'boot'"],
        "runcmd": ["echo 'run'"],
        "users": [
            {
                "name": "testuser",
                "gecos": "Test User",
                "sudo": "ALL=(ALL) NOPASSWD:ALL",
                "ssh_authorized_keys": ["ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDtest"],
            }
        ],
        "fqdn": "testvm.example.com",
    }


@pytest.fixture
def mock_domain():
    """Create a mock LibvirtDomain."""
    domain = Mock()
    domain.name = "testvm"
    domain.fqdn = "testvm.example.com"
    domain.ssh_key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDtest"
    domain.root_password = "testpass"
    domain.username = "testuser"
    
    domain.dom = Mock()
    domain.dom.UUIDString.return_value = "12345678-1234-1234-1234-123456789abc"
    
    domain.user_data = {
        "resize_rootfs": True,
        "disable_root": False,
        "bootcmd": [],
        "runcmd": [],
    }
    
    domain.nics = [
        {
            "network": "default",
            "mac": "52:54:00:12:34:56",
            "ipv4": IPv4Interface("192.168.122.10/24"),
        }
    ]
    
    return domain


@pytest.fixture
def mock_hv():
    """Create a mock LibvirtHypervisor."""
    hv = Mock()
    hv.dns = Mock()
    hv.dns.ip = "192.168.122.1"
    hv.get_network_gateway = Mock(return_value=IPv4Interface("192.168.122.1/24"))
    return hv


class TestNetworkInterface:
    """Test NetworkInterface dataclass."""

    def test_network_interface_creation(self):
        """Test creating a NetworkInterface."""
        iface = NetworkInterface(
            name="eth0",
            mac="52:54:00:12:34:56",
            ipv4=IPv4Interface("192.168.122.10/24"),
            gateway=IPv4Interface("192.168.122.1/24"),
            dns_nameservers=["192.168.122.1"],
        )
        
        assert iface.name == "eth0"
        assert iface.mac == "52:54:00:12:34:56"
        assert iface.ipv4 == IPv4Interface("192.168.122.10/24")
        assert iface.gateway == IPv4Interface("192.168.122.1/24")
        assert iface.dns_nameservers == ["192.168.122.1"]

    def test_network_interface_dhcp(self):
        """Test creating a NetworkInterface with DHCP (None ipv4)."""
        iface = NetworkInterface(
            name="eth0",
            mac="52:54:00:12:34:56",
            ipv4=None,
            gateway=IPv4Interface("192.168.122.1/24"),
            dns_nameservers=["192.168.122.1"],
        )
        
        assert iface.ipv4 is None


class TestUserDataFromDomain:
    """Test UserData.from_domain() factory method."""

    def test_from_domain_basic(self, mock_domain, mock_hv):
        """Test creating UserData from domain and hypervisor."""
        userdata = OpenStackUserData.from_domain(mock_domain, mock_hv)
        
        assert userdata.hostname == "testvm"
        assert userdata.fqdn == "testvm.example.com"
        assert userdata.instance_id == "12345678-1234-1234-1234-123456789abc"
        assert userdata.ssh_public_key == "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDtest"
        assert userdata.root_password == "testpass"
        assert userdata.username == "testuser"
        assert userdata.global_dns == ["192.168.122.1"]
        assert userdata.cloud_config == mock_domain.user_data

    def test_from_domain_builds_interfaces(self, mock_domain, mock_hv):
        """Test that from_domain correctly builds NetworkInterface list."""
        userdata = OpenStackUserData.from_domain(mock_domain, mock_hv)
        
        assert len(userdata.interfaces) == 1
        iface = userdata.interfaces[0]
        assert iface.name == "eth0"
        assert iface.mac == "52:54:00:12:34:56"
        assert iface.ipv4 == IPv4Interface("192.168.122.10/24")
        assert iface.gateway == IPv4Interface("192.168.122.1/24")
        assert iface.dns_nameservers == ["192.168.122.1"]

    def test_from_domain_multiple_nics(self, mock_domain, mock_hv):
        """Test from_domain with multiple NICs."""
        mock_domain.nics = [
            {
                "network": "default",
                "mac": "52:54:00:12:34:56",
                "ipv4": IPv4Interface("192.168.122.10/24"),
            },
            {
                "network": "private",
                "mac": "52:54:00:12:34:57",
                "ipv4": None,  # DHCP
            },
        ]
        
        mock_hv.get_network_gateway = Mock(side_effect=[
            IPv4Interface("192.168.122.1/24"),
            IPv4Interface("10.0.0.1/24"),
        ])
        
        userdata = CloudInit22UserData.from_domain(mock_domain, mock_hv)
        
        assert len(userdata.interfaces) == 2
        assert userdata.interfaces[0].name == "eth0"
        assert userdata.interfaces[0].ipv4 == IPv4Interface("192.168.122.10/24")
        assert userdata.interfaces[1].name == "eth1"
        assert userdata.interfaces[1].ipv4 is None


class TestOpenStackUserData:
    """Test OpenStackUserData class."""

    def test_iso_label(self, sample_interfaces, sample_cloud_config):
        """Test OpenStackUserData returns correct ISO label."""
        userdata = OpenStackUserData(
            hostname="testvm",
            fqdn="testvm.example.com",
            instance_id="test-uuid",
            ssh_public_key="ssh-rsa test",
            root_password="testpass",
            username="testuser",
            interfaces=sample_interfaces,
            global_dns=["192.168.122.1"],
            cloud_config=sample_cloud_config,
        )
        
        assert userdata.iso_label() == "config-2"

    def test_iso_args(self, sample_interfaces, sample_cloud_config):
        """Test OpenStackUserData returns correct ISO generation args."""
        userdata = OpenStackUserData(
            hostname="testvm",
            fqdn="testvm.example.com",
            instance_id="test-uuid",
            ssh_public_key="ssh-rsa test",
            root_password="testpass",
            username="testuser",
            interfaces=sample_interfaces,
            global_dns=["192.168.122.1"],
            cloud_config=sample_cloud_config,
        )
        
        args = userdata.iso_args()
        assert "-ldots" in args
        assert "-allow-lowercase" in args
        assert "-allow-multidot" in args
        assert "-J" in args  # OpenStack uses -J, not -joliet
        assert "-r" in args

    def test_render_creates_openstack_structure(self, sample_interfaces, sample_cloud_config):
        """Test render() creates correct OpenStack directory structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            
            userdata = OpenStackUserData(
                hostname="testvm",
                fqdn="testvm.example.com",
                instance_id="test-uuid",
                ssh_public_key="ssh-rsa test",
                root_password="testpass",
                username="testuser",
                interfaces=sample_interfaces,
                global_dns=["192.168.122.1"],
                cloud_config=sample_cloud_config,
            )
            
            userdata.render(output_dir)
            
            # Verify directory structure
            openstack_dir = output_dir / "openstack" / "latest"
            assert openstack_dir.exists()
            assert (openstack_dir / "meta_data.json").exists()
            assert (openstack_dir / "network_data.json").exists()
            assert (openstack_dir / "user_data").exists()

    def test_render_meta_data_json_content(self, sample_interfaces, sample_cloud_config):
        """Test meta_data.json has correct content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            
            userdata = OpenStackUserData(
                hostname="testvm",
                fqdn="testvm.example.com",
                instance_id="test-uuid-12345",
                ssh_public_key="ssh-rsa AAAAB3test",
                root_password="securepass",
                username="testuser",
                interfaces=sample_interfaces,
                global_dns=["192.168.122.1"],
                cloud_config=sample_cloud_config,
            )
            
            userdata.render(output_dir)
            
            meta_data_file = output_dir / "openstack" / "latest" / "meta_data.json"
            meta_data = json.loads(meta_data_file.read_text())
            
            assert meta_data["hostname"] == "testvm.example.com"
            assert meta_data["name"] == "testvm"
            assert meta_data["local-hostname"] == "testvm"
            assert meta_data["uuid"] == "test-uuid-12345"
            assert meta_data["admin_pass"] == "securepass"
            assert meta_data["public_keys"]["default"] == "ssh-rsa AAAAB3test"
            assert meta_data["availability_zone"] == "nova"

    def test_render_network_data_json_content(self, sample_interfaces, sample_cloud_config):
        """Test network_data.json has correct structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            
            userdata = OpenStackUserData(
                hostname="testvm",
                fqdn="testvm.example.com",
                instance_id="test-uuid",
                ssh_public_key="ssh-rsa test",
                root_password="testpass",
                username="testuser",
                interfaces=sample_interfaces,
                global_dns=["192.168.122.1"],
                cloud_config=sample_cloud_config,
            )
            
            userdata.render(output_dir)
            
            network_data_file = output_dir / "openstack" / "latest" / "network_data.json"
            network_data = json.loads(network_data_file.read_text())
            
            assert "links" in network_data
            assert "networks" in network_data
            assert "services" in network_data
            
            # Should have 2 links (2 interfaces)
            assert len(network_data["links"]) == 2
            assert network_data["links"][0]["ethernet_mac_address"] == "52:54:00:12:34:56"
            assert network_data["links"][1]["ethernet_mac_address"] == "52:54:00:12:34:57"
            
            # First has static IP, second is DHCP
            assert len(network_data["networks"]) == 2
            assert network_data["networks"][0]["type"] == "ipv4"
            assert network_data["networks"][0]["ip_address"] == "192.168.122.10"
            assert network_data["networks"][1]["type"] == "ipv4_dhcp"

    def test_render_user_data_content(self, sample_interfaces, sample_cloud_config):
        """Test user_data file has correct cloud-config format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            
            userdata = OpenStackUserData(
                hostname="testvm",
                fqdn="testvm.example.com",
                instance_id="test-uuid",
                ssh_public_key="ssh-rsa test",
                root_password="testpass",
                username="testuser",
                interfaces=sample_interfaces,
                global_dns=["192.168.122.1"],
                cloud_config=sample_cloud_config,
            )
            
            userdata.render(output_dir)
            
            user_data_file = output_dir / "openstack" / "latest" / "user_data"
            user_data_content = user_data_file.read_text()
            
            # Should start with cloud-config header
            assert user_data_content.startswith("#cloud-config\n")
            
            # Parse YAML content
            yaml_content = user_data_content[len("#cloud-config\n"):]
            parsed = yaml.safe_load(yaml_content)
            
            assert parsed["resize_rootfs"] is True
            assert parsed["password"] == "testpass"
            assert parsed["fqdn"] == "testvm.example.com"


class TestCloudInit22UserData:
    """Test CloudInit22UserData class (NoCloud v1)."""

    def test_iso_label(self, sample_interfaces, sample_cloud_config):
        """Test CloudInit22UserData returns correct ISO label."""
        userdata = CloudInit22UserData(
            hostname="testvm",
            fqdn=None,
            instance_id="test-uuid",
            ssh_public_key="ssh-rsa test",
            root_password="testpass",
            username="testuser",
            interfaces=sample_interfaces,
            global_dns=["192.168.122.1"],
            cloud_config=sample_cloud_config,
        )
        
        assert userdata.iso_label() == "cidata"

    def test_iso_args(self, sample_interfaces, sample_cloud_config):
        """Test CloudInit22UserData returns correct ISO args."""
        userdata = CloudInit22UserData(
            hostname="testvm",
            fqdn=None,
            instance_id="test-uuid",
            ssh_public_key="ssh-rsa test",
            root_password="testpass",
            username="testuser",
            interfaces=sample_interfaces,
            global_dns=["192.168.122.1"],
            cloud_config=sample_cloud_config,
        )
        
        args = userdata.iso_args()
        assert "-joliet" in args
        assert "-R" in args

    def test_render_creates_nocloud_files(self, sample_interfaces, sample_cloud_config):
        """Test render() creates NoCloud files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            
            userdata = CloudInit22UserData(
                hostname="testvm",
                fqdn=None,
                instance_id="test-uuid",
                ssh_public_key="ssh-rsa test",
                root_password="testpass",
                username="testuser",
                interfaces=sample_interfaces,
                global_dns=["192.168.122.1"],
                cloud_config=sample_cloud_config,
            )
            
            userdata.render(output_dir)
            
            # Verify NoCloud files
            assert (output_dir / "user-data").exists()
            assert (output_dir / "meta-data").exists()
            assert (output_dir / "network-config").exists()

    def test_network_config_v1_structure(self, sample_interfaces, sample_cloud_config):
        """Test network-config uses v1 format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            
            userdata = CloudInit22UserData(
                hostname="testvm",
                fqdn=None,
                instance_id="test-uuid",
                ssh_public_key="ssh-rsa test",
                root_password="testpass",
                username="testuser",
                interfaces=sample_interfaces,
                global_dns=["192.168.122.1"],
                cloud_config=sample_cloud_config,
            )
            
            userdata.render(output_dir)
            
            network_config_file = output_dir / "network-config"
            network_config = yaml.safe_load(network_config_file.read_text())
            
            assert network_config["version"] == 1
            assert "config" in network_config
            assert len(network_config["config"]) == 2
            
            # First interface (static)
            eth0 = network_config["config"][0]
            assert eth0["type"] == "physical"
            assert eth0["name"] == "eth0"
            assert eth0["mac_address"] == "52:54:00:12:34:56"
            assert eth0["subnets"][0]["type"] == "static"
            assert eth0["subnets"][0]["address"] == "192.168.122.10/24"
            assert eth0["subnets"][0]["gateway"] == "192.168.122.1"
            
            # Second interface (DHCP)
            eth1 = network_config["config"][1]
            assert eth1["name"] == "eth1"
            assert eth1["subnets"][0]["type"] == "dhcp"

    def test_meta_data_eni_format(self, sample_interfaces, sample_cloud_config):
        """Test meta-data uses legacy ENI format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            
            userdata = CloudInit22UserData(
                hostname="testvm",
                fqdn=None,
                instance_id="test-uuid",
                ssh_public_key="ssh-rsa test",
                root_password="testpass",
                username="testuser",
                interfaces=sample_interfaces,
                global_dns=["192.168.122.1"],
                cloud_config=sample_cloud_config,
            )
            
            userdata.render(output_dir)
            
            meta_data_file = output_dir / "meta-data"
            meta_data_content = meta_data_file.read_text()
            
            # Should contain ENI-style network configuration
            assert "dsmode: local" in meta_data_content
            assert "instance-id: iid-testvm" in meta_data_content
            assert "local-hostname: testvm" in meta_data_content
            assert "network-interfaces:" in meta_data_content
            assert "iface eth0 inet static" in meta_data_content
            assert "address 192.168.122.10" in meta_data_content


class TestCloudInit23UserData:
    """Test CloudInit23UserData class (NoCloud v2)."""

    def test_iso_label(self, sample_interfaces, sample_cloud_config):
        """Test CloudInit23UserData returns correct ISO label."""
        userdata = CloudInit23UserData(
            hostname="testvm",
            fqdn=None,
            instance_id="test-uuid-123",
            ssh_public_key="ssh-rsa test",
            root_password="testpass",
            username="testuser",
            interfaces=sample_interfaces,
            global_dns=["192.168.122.1"],
            cloud_config=sample_cloud_config,
        )
        
        assert userdata.iso_label() == "cidata"

    def test_network_config_v2_structure(self, sample_interfaces, sample_cloud_config):
        """Test network-config uses v2 format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            
            userdata = CloudInit23UserData(
                hostname="testvm",
                fqdn=None,
                instance_id="test-uuid",
                ssh_public_key="ssh-rsa test",
                root_password="testpass",
                username="testuser",
                interfaces=sample_interfaces,
                global_dns=["192.168.122.1"],
                cloud_config=sample_cloud_config,
            )
            
            userdata.render(output_dir)
            
            network_config_file = output_dir / "network-config"
            network_config = yaml.safe_load(network_config_file.read_text())
            
            assert network_config["version"] == 2
            assert "ethernets" in network_config
            
            # First interface (static)
            eth0 = network_config["ethernets"]["eth0"]
            assert eth0["match"]["macaddress"] == "52:54:00:12:34:56"
            assert eth0["addresses"] == ["192.168.122.10/24"]
            assert eth0["routes"][0]["to"] == "default"
            assert eth0["routes"][0]["via"] == "192.168.122.1"
            assert eth0["nameservers"]["addresses"] == ["192.168.122.1"]
            
            # Second interface (DHCP)
            eth1 = network_config["ethernets"]["eth1"]
            assert eth1["dhcp4"] is True

    def test_meta_data_yaml_format(self, sample_interfaces, sample_cloud_config):
        """Test meta-data uses YAML format (not ENI)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            
            userdata = CloudInit23UserData(
                hostname="testvm",
                fqdn=None,
                instance_id="test-uuid-456",
                ssh_public_key="ssh-rsa test",
                root_password="testpass",
                username="testuser",
                interfaces=sample_interfaces,
                global_dns=["192.168.122.1"],
                cloud_config=sample_cloud_config,
            )
            
            userdata.render(output_dir)
            
            meta_data_file = output_dir / "meta-data"
            meta_data_content = meta_data_file.read_text()
            
            # Should be YAML, not ENI format
            meta_data = yaml.safe_load(meta_data_content)
            
            assert meta_data["instance-id"] == "test-uuid-456"
            assert meta_data["local-hostname"] == "testvm"
            # Should NOT contain ENI-style network-interfaces
            assert "network-interfaces" not in meta_data_content


class TestUserDataBuildISO:
    """Test UserData.build_iso() method."""

    @patch('subprocess.run')
    def test_build_iso_calls_genisoimage(self, mock_run, sample_interfaces, sample_cloud_config):
        """Test build_iso() calls genisoimage with correct arguments."""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = Path(tmpdir)
            iso_binary = Path("/usr/bin/genisoimage")
            
            userdata = OpenStackUserData(
                hostname="testvm",
                fqdn="testvm.example.com",
                instance_id="test-uuid",
                ssh_public_key="ssh-rsa test",
                root_password="testpass",
                username="testuser",
                interfaces=sample_interfaces,
                global_dns=["192.168.122.1"],
                cloud_config=sample_cloud_config,
            )
            
            userdata.build_iso("testvm", iso_binary, temp_dir)
            
            # Verify subprocess.run was called
            assert mock_run.called
            call_args = mock_run.call_args[0][0]
            
            # Verify command structure
            assert str(iso_binary) in call_args
            assert "-output" in call_args
            assert "testvm-cidata.iso" in call_args
            assert "-volid" in call_args
            assert "config-2" in call_args

    @patch('subprocess.run')
    def test_build_iso_renders_files_first(self, mock_run, sample_interfaces, sample_cloud_config):
        """Test build_iso() renders files before calling genisoimage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = Path(tmpdir)
            iso_binary = Path("/usr/bin/genisoimage")
            
            userdata = CloudInit22UserData(
                hostname="testvm",
                fqdn=None,
                instance_id="test-uuid",
                ssh_public_key="ssh-rsa test",
                root_password="testpass",
                username="testuser",
                interfaces=sample_interfaces,
                global_dns=["192.168.122.1"],
                cloud_config=sample_cloud_config,
            )
            
            userdata.build_iso("testvm", iso_binary, temp_dir)
            
            # Verify files were created
            cd_dir = temp_dir / "cd_dir"
            assert (cd_dir / "user-data").exists()
            assert (cd_dir / "meta-data").exists()
            assert (cd_dir / "network-config").exists()
