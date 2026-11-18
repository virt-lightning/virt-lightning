from unittest.mock import Mock

import virt_lightning.api as api


def test_ssh_config_with_groups(hv):
    domain = hv.create_domain(name="esxi1", distro="esxi-6.7")
    domain.context = "default"
    domain.username = "root"
    domain.groups = ["all_esxi", "esxi_lab"]
    domain.ipv4 = "1.0.0.5/24"
    configuration = Mock(libvirt_uri="test:///default")

    output = api.ssh_config(configuration=configuration)

    assert output == (
        "Host esxi1\n"
        "     Hostname 1.0.0.5\n"
        "     User root\n"
        "     IdentityFile None\n"
    )
