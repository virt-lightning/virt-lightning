"""
Tests for metadata module, including DomainConfig merge functionality.
"""
import pytest
from virt_lightning.metadata import DomainConfig


class TestDomainConfigMerge:
    """Test DomainConfig.merge_with() method."""

    def test_merge_user_overrides_distro_for_simple_fields(self):
        """User config non-None values should override distro defaults."""
        distro_config = DomainConfig(
            memory=2048,
            vcpus=2,
            username="distro_user",
            root_password="distro_pass",
            python_interpreter="/usr/bin/python2",
        )
        
        user_config = DomainConfig(
            memory=4096,
            username="my_user",
            vcpus=None,  # Should use distro default
            root_password=None,  # Should use distro default
            python_interpreter=None,  # Should use distro default
        )
        
        merged = user_config.merge_with(distro_config)
        
        # User values override
        assert merged.memory == 4096
        assert merged.username == "my_user"
        
        # Distro defaults used where user passed None
        assert merged.vcpus == 2
        assert merged.root_password == "distro_pass"
        assert merged.python_interpreter == "/usr/bin/python2"

    def test_merge_empty_user_config_uses_all_distro_defaults(self):
        """Empty user config (all None) should result in all distro values."""
        distro_config = DomainConfig(
            memory=2048,
            vcpus=4,
            username="distro_user",
            root_password="distro_pass",
            default_nic_model="e1000",
        )
        
        # Pass None for all fields explicitly
        user_config = DomainConfig(
            memory=None,
            vcpus=None,
            username=None,
            root_password=None,
            default_nic_model=None,
        )
        
        merged = user_config.merge_with(distro_config)
        
        assert merged.memory == 2048
        assert merged.vcpus == 4
        assert merged.username == "distro_user"
        assert merged.root_password == "distro_pass"
        assert merged.default_nic_model == "e1000"

    def test_merge_list_fields_user_nonempty_overrides(self):
        """Non-empty user lists should override distro lists."""
        distro_config = DomainConfig(
            groups=["distro_group1", "distro_group2"],
            bootcmd=["echo distro"],
            runcmd=["ls /distro"],
        )
        
        user_config = DomainConfig(
            groups=["user_group"],
            bootcmd=["echo user"],
            # runcmd not set
        )
        
        merged = user_config.merge_with(distro_config)
        
        # User lists override
        assert merged.groups == ["user_group"]
        assert merged.bootcmd == ["echo user"]
        
        # Empty user list means use distro list
        assert merged.runcmd == ["ls /distro"]

    def test_merge_list_fields_empty_user_uses_distro(self):
        """Empty user lists should use distro lists."""
        distro_config = DomainConfig(
            groups=["distro_group"],
            bootcmd=["echo distro"],
        )
        
        user_config = DomainConfig(
            groups=[],  # Explicitly empty
            bootcmd=[],  # Explicitly empty
        )
        
        merged = user_config.merge_with(distro_config)
        
        assert merged.groups == ["distro_group"]
        assert merged.bootcmd == ["echo distro"]

    def test_merge_preserves_user_fqdn(self):
        """User-specified FQDN should override distro FQDN."""
        distro_config = DomainConfig(fqdn="distro.example.com")
        user_config = DomainConfig(fqdn="user.example.com")
        
        merged = user_config.merge_with(distro_config)
        
        assert merged.fqdn == "user.example.com"

    def test_merge_none_values_use_distro_defaults(self):
        """None values in user config should use distro values."""
        distro_config = DomainConfig(
            fqdn="distro.example.com",
            ssh_key_file="/distro/key",
        )
        
        user_config = DomainConfig(
            fqdn=None,
            ssh_key_file=None,
        )
        
        merged = user_config.merge_with(distro_config)
        
        assert merged.fqdn == "distro.example.com"
        assert merged.ssh_key_file == "/distro/key"

    def test_merge_all_fields_coverage(self):
        """Verify merge works for all DomainConfig fields."""
        distro_config = DomainConfig(
            groups=["distro_group"],
            memory=2048,
            python_interpreter="/usr/bin/python2",
            root_password="distro_root",
            ssh_key_file="/distro/key",
            username="distro_user",
            vcpus=2,
            fqdn="distro.example.com",
            default_nic_model="e1000",
            bootcmd=["echo distro"],
            runcmd=["ls distro"],
            meta_data_media_type="floppy",
            default_bus_type="ide",
        )
        
        user_config = DomainConfig(
            groups=["user_group"],
            memory=4096,
            python_interpreter=None,  # use distro
            root_password="user_root",
            ssh_key_file=None,  # use distro
            username="user_name",
            vcpus=8,
            fqdn="user.example.com",
            default_nic_model=None,  # use distro
            bootcmd=["echo user"],
            runcmd=None,  # use distro (will be handled as empty list → use distro)
            meta_data_media_type="cdrom",
            default_bus_type=None,  # use distro
        )
        
        merged = user_config.merge_with(distro_config)
        
        # User overrides
        assert merged.groups == ["user_group"]
        assert merged.memory == 4096
        assert merged.root_password == "user_root"
        assert merged.username == "user_name"
        assert merged.vcpus == 8
        assert merged.fqdn == "user.example.com"
        assert merged.bootcmd == ["echo user"]
        assert merged.meta_data_media_type == "cdrom"
        
        # Distro defaults
        assert merged.python_interpreter == "/usr/bin/python2"
        assert merged.ssh_key_file == "/distro/key"
        assert merged.default_nic_model == "e1000"
        assert merged.runcmd == ["ls distro"]
        assert merged.default_bus_type == "ide"
