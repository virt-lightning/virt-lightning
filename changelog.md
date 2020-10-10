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
