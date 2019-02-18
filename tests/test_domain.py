import virt_lightning

import pathlib
from unittest.mock import patch
import libvirt

IF_XML = """
<domain>
  <devices>
    <interface type='bridge'>
      <mac address='52:54:00:d7:92:5b'/>
    </interface>
  </devices>
</domain>
"""


def test_name(domain):
    assert domain.name == "a"

def test_context(domain):
    assert domain.context == None
    domain.context = "something"
    assert domain.context == "something"

def test_load_ssh_key(domain, tmp_path):
    CONTENT = "dummy ssh key"
    p = tmp_path / "id_rsa.pub"
    p.write_text(CONTENT)

    domain.load_ssh_key_file(p)
    assert domain.ssh_key == CONTENT

def test_mac_addresses(domain):
    def xmlDesc(i):
        return IF_XML
    with patch.object(domain.dom, 'XMLDesc', xmlDesc) as mock_xmldesc:
        print(domain.mac_addresses)
        assert domain.mac_addresses
