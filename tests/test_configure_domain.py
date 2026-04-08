"""
Tests for configure_domain to verify merge behavior.
"""
from unittest.mock import MagicMock

import pytest

from virt_lightning.metadata import DomainConfig
from virt_lightning.virt_lightning import LibvirtDomain, LibvirtHypervisor


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
    monkeypatch.setitem(__import__("sys").modules, "libvirt", mock_libvirt)
    monkeypatch.setitem(__import__("sys").modules, "ipaddress", MagicMock())




@pytest.fixture
def mock_hv():
    """Create a mock hypervisor."""
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
    dom.UUIDString.return_value = "test-uuid-12345"
    dom._metadata_store = {}

    def set_metadata_mock(meta_type, meta, namespace, uri, flags):
        # Simple simulation of how libvirt stores metadata
        import re
        match = re.search(r"<(\w+) name='([^']*)' />", meta)
        if match:
            value = match.group(2)
            dom._metadata_store[uri] = {"xml": meta, "value": value}

    def get_metadata_mock(meta_type, uri):
        if uri in dom._metadata_store:
            return dom._metadata_store[uri]["xml"]
        err = mock_libvirt.libvirtError("No domain metadata")
        err.get_error_code = lambda: mock_libvirt.VIR_ERR_NO_DOMAIN_METADATA
        raise err

    dom.setMetadata.side_effect = set_metadata_mock
    dom.metadata.side_effect = get_metadata_mock

    domain = LibvirtDomain(dom)
    domain.distro = "test-distro"
    return domain


class TestConfigureDomain:
    """Test that configure_domain properly merges user and distro configs."""

    def test_configure_domain_merges_user_with_distro(self, mock_hv, mock_domain, tmp_path):
        """configure_domain should merge user_config with distro config."""
        # Create a fake distro config file
        distro_dir = tmp_path / "upstream"
        distro_dir.mkdir()

        # Create distro config
        distro_config_file = distro_dir / "test-distro.yaml"
        distro_config_file.write_text("""memory: 2048
vcpus: 2
username: distro_user
root_password: distro_pass
python_interpreter: /usr/bin/python2
default_nic_model: e1000
""")

        # Mock get_storage_dir to return our tmp_path
        mock_hv.get_storage_dir = MagicMock(return_value=tmp_path)

        # Create user config that overrides some values
        user_config = DomainConfig(
            memory=4096,
            username="my_user",
            # vcpus, root_password, python_interpreter not set - should use distro defaults
        )

        mock_hv.configure_domain(mock_domain, user_config)

        # Verify merged values were applied by checking that setters were called
        # User overrides
        assert mock_domain.dom.setMemoryFlags.called
        # Check memory was set to 4096 MB (4096 * 1024 KiB)
        calls = [call for call in mock_domain.dom.setMemoryFlags.call_args_list
                 if call[0][0] == 4096 * 1024]
        assert len(calls) > 0, "Memory should be set to 4096 MB"

        # Verify username via metadata
        assert mock_domain.get_metadata("username") is not None
        # Distro defaults
        assert mock_domain.dom.setVcpusFlags.called
        assert mock_domain.get_metadata("root_password") is not None
        assert mock_domain.get_metadata("python_interpreter") is not None

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
        )

        mock_hv.configure_domain(mock_domain, user_config)

        # Verify user values were applied
        # Check memory was set to 8192 MB
        memory_calls = [call for call in mock_domain.dom.setMemoryFlags.call_args_list
                        if call[0][0] == 8192 * 1024]
        assert len(memory_calls) > 0, "Memory should be set to 8192 MB"

        # Check vcpus was set to 4
        vcpu_calls = [call for call in mock_domain.dom.setVcpusFlags.call_args_list
                      if call[0][0] == 4]
        assert len(vcpu_calls) > 0, "VCPUs should be set to 4"

        # Check username via metadata
        username_meta = mock_domain.get_metadata("username")
        assert username_meta is not None
        assert "custom_user" in username_meta

    def test_configure_domain_empty_user_uses_distro_defaults(self, mock_hv, mock_domain, tmp_path):
        """Empty user config should result in all distro defaults being used."""
        distro_dir = tmp_path / "upstream"
        distro_dir.mkdir()

        # Now create distro config
        distro_config_file = distro_dir / "test-distro.yaml"
        distro_config_file.write_text("""memory: 2048
vcpus: 2
username: distro_user
root_password: distro_pass
default_nic_model: rtl8139
""")

        mock_hv.get_storage_dir = MagicMock(return_value=tmp_path)

        # Empty user config - pass None to use distro defaults
        user_config = DomainConfig(
            memory=None,
            vcpus=None,
            username=None,
            root_password=None,
            default_nic_model=None,
        )

        mock_hv.configure_domain(mock_domain, user_config)

        # Verify all distro values were applied
        # Check memory was set to 2048 MB
        memory_calls = [call for call in mock_domain.dom.setMemoryFlags.call_args_list
                        if call[0][0] == 2048 * 1024]
        assert len(memory_calls) > 0, "Memory should be set to 2048 MB"

        # Check vcpus was set to 2
        vcpu_calls = [call for call in mock_domain.dom.setVcpusFlags.call_args_list
                      if call[0][0] == 2]
        assert len(vcpu_calls) > 0, "VCPUs should be set to 2"

        # Check distro values via metadata
        assert mock_domain.get_metadata("username") is not None
        assert "distro_user" in mock_domain.get_metadata("username")
        assert mock_domain.get_metadata("root_password") is not None
        assert "distro_pass" in mock_domain.get_metadata("root_password")

        # Check default_nic_model was set
        assert mock_domain.default_nic_model == "rtl8139"
