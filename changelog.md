# 2.3.0

- tox: add "build" target
- run tox with Github Action
- move from setup.py to pyproject.toml
- cloudinit: add a workaround for the DNS and Fedora
- github: add a ruff-based test
- Add CodeQL workflow for GitHub code scanning (#257)
- Set the Source project URL in setup.py
- reindent with black
- Implement disk size parameter for 'start' command

# 2.2.0

- Cosmetic documentation changes
- Don't try to fetch an image that already exists
- Add ability to boot old system with no virtio support
- Use Libvirt default settings when possible
- Use the VNC display by default
- Add support for OpenVSwitch (a.k.a OVS )bridge
- vl stop: avoid a Python backtrace if the VM doesn't exist

# 2.1.1

- reconnect to libvirt after the download step (#218)

# 2.1.0

- distro displayed in vl status output (#199)
- support config for private image hub (#193)
- expose the runcmd list
- api: reuse the MAC only if an IPv4 is def
- ansible_inventory: disable Kerberos auth by default
- clarify some error message
- fix `vl distro_list` output to be compatible with the `virt-lightning.yaml` format (#203)

# 2.0.1

Minor release.

- Deprecate the manual build of the images
- When an image is missing, the error show up an URL pointing on a list of
  excepted image names
- fix the ssh and console parameters
- properly handle large master image by raising the size of the backing file

# 2.0.0

Main change is the introduction of the api module. It exposes a public API.

- api.py: new public API module
- shell.py: consume `api.py`
- `attachNetwork()` is now called `attach_network()`
- `getNextBlckDevice()` is now `get_next_block_device()`
- `attachDisk()` is now `attach_disk()`
- the `mac_address()` method has been remove method has been removedd

# 1.1.0

Main changes are the RHEL8 support and `fetch` action to retrieve images:

- enable static typing check (mypy)
- ensure get_distro_configuration() return dict
- import ubuntu-14.04 distro script
- README: document the configuration keys
- ability to manually set the IP address
- ability to set the FQDN
- metadata: pass the root_password in `admin_pass`
- openstack meta: preserve long file name
- memory: set the current the amount of memory
- `start`: add the `--name` argument
- centos: don't need NetworkManager anymore
- Add `ssh_config` CLI command
- add new images
- vcpu: correctly cap the number of CPU
- remove `iconify()` function
- remove the swap disk
- test: remove a dup of `test_create_disk`
- add ability to define several NIC
- improve the low memory warning
- use distro specific configuration
- add the `fetch` action
- on RHEL8, kvm is in /usr/libexec
- use openstack metadata format by default
- clean up the network
- improve distro specific config managment
- start: pass --memory and --vcpus properly
- hostname autogeneration: allow - char
- root_disk_size: default at 15G again
- add new images
- test: coverage for create_disk()
- black: refresh the indentation
- flake8: ignore T001 errors
- README.md: remove the template system

# 1.0.0

Initial release
