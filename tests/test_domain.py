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


def test_vcpus(domain):
    assert domain.vcpus > 0
    domain.vcpus = 2
    assert domain.vcpus == 2


def test_fqdn(domain):
    domain.fqdn = "my.test"
    assert domain.fqdn == "my.test"
