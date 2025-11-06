import pytest
import re
from unittest.mock import MagicMock, patch, mock_open

class LibvirtError(Exception):
    def __init__(self, msg=""):
        super().__init__(msg)
    def get_error_code(self):
        return 0

mock_libvirt = MagicMock()
mock_libvirt.libvirtError = LibvirtError
mock_libvirt.VIR_DOMAIN_METADATA_ELEMENT = 2
mock_libvirt.VIR_ERR_NO_DOMAIN_METADATA = 55 # Using a known constant value
mock_libvirt.VIR_DOMAIN_AFFECT_CONFIG = 2

@pytest.fixture(autouse=True)
def mock_imports(monkeypatch):
    monkeypatch.setitem(__import__('sys').modules, 'libvirt', mock_libvirt)
    monkeypatch.setitem(__import__('sys').modules, 'ipaddress', MagicMock())
    # Mock the logger to prevent errors if it's not configured
    monkeypatch.setitem(__import__('sys').modules, 'logger', MagicMock())


from virt_lightning.virt_lightning import LibvirtDomain

@pytest.fixture
def mock_dom():
    """Pytest fixture to create a mocked libvirt domain object."""
    domain = MagicMock()
    domain.name.return_value = "test-vm"
    # Mock the metadata storage
    domain._metadata_store = {}

    def set_metadata_mock(meta_type, meta, namespace, uri, flags):
        # A simple simulation of how libvirt stores metadata
        match = re.search(r"<(\w+) name='([^']*)' />", meta)
        if match:
            key = match.group(1)
            value = match.group(2)
            domain._metadata_store[uri] = {'xml': meta, 'value': value}

    def get_metadata_mock(meta_type, uri):
        if uri in domain._metadata_store:
            return domain._metadata_store[uri]['xml']
        err = mock_libvirt.libvirtError("No domain metadata")
        err.get_error_code = lambda: mock_libvirt.VIR_ERR_NO_DOMAIN_METADATA
        raise err

    domain.setMetadata.side_effect = set_metadata_mock
    domain.metadata.side_effect = get_metadata_mock
    return domain

@pytest.fixture
def libvirt_domain(mock_dom):
    """Fixture to create a LibvirtDomain instance with a mocked domain."""
    return LibvirtDomain(mock_dom)


def test_initialization(libvirt_domain):
    """Test that the class is initialized with correct default user_data."""
    assert libvirt_domain.user_data == {
        "resize_rootfs": True,
        "disable_root": 0,
        "bootcmd": [],
        "runcmd": [],
    }
    assert libvirt_domain.ssh_key is None
    assert libvirt_domain.nics == []


def test_root_password_setter(libvirt_domain, mock_dom):
    """Test setting the root_password property."""
    password = "supersecret"
    libvirt_domain.root_password = password

    # Verify user_data is updated
    assert libvirt_domain.user_data["disable_root"] is False
    assert libvirt_domain.user_data["password"] == password
    assert libvirt_domain.user_data["chpasswd"]["list"] == f"root:{password}\n"
    assert libvirt_domain.user_data["ssh_pwauth"] is True

    # Verify metadata was recorded
    mock_dom.setMetadata.assert_called_with(
        mock_libvirt.VIR_DOMAIN_METADATA_ELEMENT,
        f"<root_password name='{password}' />",
        "vl",
        "root_password",
        mock_libvirt.VIR_DOMAIN_AFFECT_CONFIG,
    )

def test_root_password_getter(libvirt_domain, mock_dom):
    """Test getting the root_password property."""
    password = "supersecret"
    # Set the metadata using setMetadata to simulate the setter
    mock_dom.setMetadata(
        mock_libvirt.VIR_DOMAIN_METADATA_ELEMENT,
        f"<root_password name='{password}' />",
        "vl",
        "root_password",
        mock_libvirt.VIR_DOMAIN_AFFECT_CONFIG,
    )
    
    assert libvirt_domain.root_password == password
    mock_dom.metadata.assert_called_with(mock_libvirt.VIR_DOMAIN_METADATA_ELEMENT, "root_password")

def test_load_ssh_key_file_success(libvirt_domain):
    """Test successfully loading an SSH key from a file."""
    fake_key = "ssh-rsa AAAA..."

    mock_path = MagicMock()
    mock_path.expanduser.return_value = mock_path
    mock_path.read_text.return_value = fake_key

    libvirt_domain.load_ssh_key_file(mock_path)

    assert libvirt_domain.ssh_key == fake_key
    assert libvirt_domain.user_data["ssh_authorized_keys"] == [fake_key]

def test_load_ssh_key_file_with_user(libvirt_domain):
    """Test loading an SSH key when a user already exists in user_data."""
    # Setup initial user
    libvirt_domain.user_data["users"] = [{"name": "testuser"}]
    fake_key = "ssh-rsa BBBB..."
    
    mock_path = MagicMock()
    mock_path.expanduser.return_value = mock_path
    mock_path.read_text.return_value = fake_key

    libvirt_domain.load_ssh_key_file(mock_path)
        
    assert libvirt_domain.user_data["users"][0]["ssh_authorized_keys"] == [fake_key]

def test_load_ssh_key_file_failure(libvirt_domain):
    """Test that an OSError is raised when the key file cannot be read."""
    mock_path = MagicMock()
    mock_path.expanduser.return_value = mock_path
    mock_path.read_text.side_effect = OSError("Cannot read file")

    with pytest.raises(OSError):
        libvirt_domain.load_ssh_key_file(mock_path)

def test_username_setter(libvirt_domain, mock_dom):
    """Test setting a valid username."""
    username = "valid_user"
    libvirt_domain.username = username

    # Verify user_data
    assert len(libvirt_domain.user_data["users"]) == 1
    user_dict = libvirt_domain.user_data["users"][0]
    assert user_dict["name"] == username
    assert "sudo" in user_dict

    # Verify metadata
    mock_dom.setMetadata.assert_called_with(
        mock_libvirt.VIR_DOMAIN_METADATA_ELEMENT,
        f"<username name='{username}' />",
        "vl",
        "username",
        mock_libvirt.VIR_DOMAIN_AFFECT_CONFIG,
    )

@pytest.mark.parametrize("invalid_name", ["InvalidUser", "1-start", "user-with-!", ""])
def test_username_setter_invalid(libvirt_domain, invalid_name):
    """Test that setting an invalid username raises an Exception."""
    with pytest.raises(Exception):
        libvirt_domain.username = invalid_name

def test_fqdn_setter_valid(libvirt_domain, mock_dom):
    """Test setting a valid FQDN."""
    fqdn = "myvm.example.com"
    # import pdb; pdb.set_trace()  # Debugging breakpoint
    libvirt_domain.fqdn = fqdn

    assert libvirt_domain.user_data["fqdn"] == fqdn
    mock_dom.setMetadata.assert_called_with(
        mock_libvirt.VIR_DOMAIN_METADATA_ELEMENT,
        f"<fqdn name='{fqdn}' />",
        "vl",
        "fqdn",
        mock_libvirt.VIR_DOMAIN_AFFECT_CONFIG,
    )

@pytest.mark.parametrize("invalid_fqdn", ["not_a_valid_fqdn!", " leading.space.com"])
def test_fqdn_setter_invalid(libvirt_domain, invalid_fqdn, mock_dom):
    """Test that an invalid FQDN does not update data or metadata."""
    libvirt_domain.fqdn = invalid_fqdn
    assert "fqdn" not in libvirt_domain.user_data
    mock_dom.setMetadata.assert_not_called()

@pytest.mark.parametrize("prop_name, value", [
    ("distro", "ubuntu22.04"),
    ("python_interpreter", "/usr/bin/python3.9"),
    ("context", "test-context"),
])
def test_simple_metadata_properties(libvirt_domain, mock_dom, prop_name, value):
    """Test standard metadata properties (distro, python_interpreter, context)."""
    # Set the property
    setattr(libvirt_domain, prop_name, value)

    # Verify metadata was recorded
    mock_dom.setMetadata.assert_called_with(
        mock_libvirt.VIR_DOMAIN_METADATA_ELEMENT,
        f"<{prop_name} name='{value}' />",
        "vl",
        prop_name,
        mock_libvirt.VIR_DOMAIN_AFFECT_CONFIG,
    )
    
    # Mock the return for the getter
    mock_dom.metadata.return_value = f"<{prop_name} name='{value}' />"
    
    # Verify the getter works
    assert getattr(libvirt_domain, prop_name) == value

def test_groups_property(libvirt_domain, mock_dom):
    """Test the 'groups' property for setting and getting."""
    # Test setter
    groups_list = ["sudo", "docker"]
    libvirt_domain.groups = groups_list
    
    # Verify metadata was recorded with a comma-separated string
    mock_dom.setMetadata.assert_called_with(
        mock_libvirt.VIR_DOMAIN_METADATA_ELEMENT,
        "<groups name='sudo,docker' />",
        "vl",
        "groups",
        mock_libvirt.VIR_DOMAIN_AFFECT_CONFIG,
    )

    # Test getter with value
    mock_dom.metadata.return_value = "<groups name='sudo,docker' />"
    assert libvirt_domain.groups == groups_list


@pytest.mark.parametrize("cmd_type", ["bootcmd", "runcmd"])
def test_cmd_properties(libvirt_domain, cmd_type):
    """Test bootcmd and runcmd properties."""
    commands = ["echo 'hello'", "touch /tmp/file"]
    
    # Test setter with a valid list
    setattr(libvirt_domain, cmd_type, commands)
    assert libvirt_domain.user_data[cmd_type] == commands

    # Test getter
    assert getattr(libvirt_domain, cmd_type) == commands

    # Test setter with an invalid type
    with pytest.raises(ValueError):
        setattr(libvirt_domain, cmd_type, "a string is not a list")