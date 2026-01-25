"""
Tests for configure_domain to verify merge behavior.
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
from virt_lightning.metadata import DomainConfig

# Mock libvirt before importing virt_lightning
class LibvirtError(Exception):
    def __init__(self, msg=""):
        super().__init__(msg)
    def get_error_code(self):
        return 0

mock_libvirt = MagicMock()
mock_libvirt.libvirtError = LibvirtError
mock_libvirt.VIR_DOMAIN_METADATA_ELEMENT = 2
mock_libvirt.VIR_ERR_NO_DOMAIN_METADATA = 55
mock_libvirt.VIR_DOMAIN_AFFECT_CONFIG = 2


@pytest.fixture(autouse=True)
def mock_imports(monkeypatch):
    monkeypatch.setitem(__import__('sys').modules, 'libvirt', mock_libvirt)
    monkeypatch.setitem(__import__('sys').modules, 'ipaddress', MagicMock())


from virt_lightning.virt_lightning import LibvirtHypervisor, LibvirtDomain


@pytest.fixture
def mock_hv():
    """Create a mock hypervisor."""
    hv = MagicMock(spec=LibvirtHypervisor)
    # Create a real instance for testing configure_domain
    real_hv = LibvirtHypervisor(conn=MagicMock())
    real_hv.storage_pool_obj = MagicMock()
    real_hv.storage_pool_obj.storageVolLookupByName = MagicMock(return_value=MagicMock())
    return real_hv


@pytest.fixture
def mock_domain():
    """Create a mock LibvirtDomain."""
    dom = MagicMock()
    dom.name.return_value = "test-vm"
    dom._metadata_store = {}
    
    domain = LibvirtDomain(hypervisor=MagicMock(), name="test-vm", distro="test-distro")
    domain.dom = dom
    return domain


class TestConfigureDomain:
    """Test that configure_domain properly merges user and distro configs."""

    def test_configure_domain_merges_user_with_distro(self, mock_hv, mock_domain, tmp_path):
        """configure_domain should merge user_config with distro config."""
        # Create a fake distro config file
        distro_dir = tmp_path / "upstream"
        distro_dir.mkdir()
        distro_config_file = distro_dir / "test-distro.yaml"
        distro_config_file.write_text("""
memory: 2048
vcpus: 2
username: distro_user
root_password: distro_pass
python_interpreter: /usr/bin/python2
default_nic_model: e1000
ssh_key_file: /tmp/distro_key
""")
        
        # Mock get_storage_dir to return our tmp_path
        mock_hv.get_storage_dir = MagicMock(return_value=tmp_path)
        
        # Create user config that overrides some values
        user_config = DomainConfig(
            memory=4096,
            username="my_user",
            ssh_key_file="/tmp/user_key",
            # vcpus, root_password, python_interpreter not set - should use distro defaults
        )
        
        # Mock ssh key file
        with patch('pathlib.Path.exists', return_value=True):
            with patch('pathlib.Path.open', mock_open(read_data="ssh-rsa AAAAB3...")):
                mock_hv.configure_domain(mock_domain, user_config)
        
        # Verify merged values were applied
        assert mock_domain.memory == 4096  # User override
        assert mock_domain.username == "my_user"  # User override
        assert mock_domain.vcpus == 2  # Distro default
        assert mock_domain.root_password == "distro_pass"  # Distro default
        assert mock_domain.python_interpreter == "/usr/bin/python2"  # Distro default
        assert mock_domain.default_nic_model == "e1000"  # Distro default

    def test_configure_domain_no_distro_file_uses_user_config(self, mock_hv, mock_domain, tmp_path):
        """If no distro config exists, should use user config with DomainConfig defaults."""
        # Setup empty upstream directory
        distro_dir = tmp_path / "upstream"
        distro_dir.mkdir()
        mock_hv.get_storage_dir = MagicMock(return_value=tmp_path)
        
        user_config = DomainConfig(
            memory=8192,
            vcpus=4,
            username="custom_user",
            ssh_key_file="/tmp/my_key",
        )
        
        with patch('pathlib.Path.exists', return_value=True):
            with patch('pathlib.Path.open', mock_open(read_data="ssh-rsa AAAAB3...")):
                mock_hv.configure_domain(mock_domain, user_config)
        
        # Should get user values
        assert mock_domain.memory == 8192
        assert mock_domain.vcpus == 4
        assert mock_domain.username == "custom_user"

    def test_configure_domain_empty_user_uses_distro_defaults(self, mock_hv, mock_domain, tmp_path):
        """Empty user config should result in all distro defaults being used."""
        distro_dir = tmp_path / "upstream"
        distro_dir.mkdir()
        distro_config_file = distro_dir / "test-distro.yaml"
        distro_config_file.write_text("""
memory: 2048
vcpus: 2
username: distro_user
root_password: distro_pass
ssh_key_file: /tmp/distro_key
default_nic_model: rtl8139
""")
        
        mock_hv.get_storage_dir = MagicMock(return_value=tmp_path)
        
        # Empty user config
        user_config = DomainConfig()
        
        with patch('pathlib.Path.exists', return_value=True):
            with patch('pathlib.Path.open', mock_open(read_data="ssh-rsa AAAAB3...")):
                mock_hv.configure_domain(mock_domain, user_config)
        
        # Should get all distro values
        assert mock_domain.memory == 2048
        assert mock_domain.vcpus == 2
        assert mock_domain.username == "distro_user"
        assert mock_domain.root_password == "distro_pass"
        assert mock_domain.default_nic_model == "rtl8139"
