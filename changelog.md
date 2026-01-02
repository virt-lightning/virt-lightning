# 2.4.1

- remove tox and flake8
- (origin/main) migrate to uv
- (github/main, github/HEAD) update the image list
- shell: put back "fetch" in the action list
- Create CNAME
- Update images
- Rerun refresh.py
- refresh.py: fix base_url of for fedora images
- refresh.py: add AlpineLinux images
- GHA: add a release pipeline

# 2.4.0

- SSH key: dynamic file lookup
- black: fix virt_lightning.api
- update image list
- add support for a user defined image list
- tox: refresh the py versions
- fetch: don't use virt-lightning.org anymore
- config: bump the default memory from 768MB to 1024MB
- add NetBSD 10.1
- Add FreeBSD 14.2
- refresh.py: Support overriding python_interpreter via images_data.json
- README: add a note to explain how to adjust the ansible_python_interpreter
- Inventory update in Readme
- pyproject: update ruff configuration key names
- add images.json and refresh the image lists
- Fix for inventory template
- Add more documentation about interface configuration variable
- Add additional network addresses to Ansible inventory
- netbsd-9.3: fix the URL (#314)
- distro: add FreeBSD 13.2 and FreeBSD 14.0 (#313)
- virt-lightning.org: also update the README.md (#308)
- README: explain how to install on Silverblue (#307)
- README: explain how to use a different loc for the SSH key
- centos-n-stream renamed to centos-stream-n (#305)
- update docs and cli help response
- update centos stream images
- Update README.md
- Update README.md
- CI: enable py312
- distro: add Fedora-40
- distro: add Debian 13 (Trixie)
- distro: add Ubuntu 23.10 and 24.04
- flake8: Address a series of warnings
- Update flake8 for Python 3.12 support

# 2.3.2

- Fixed error message for missing genisoimage
- Remove and replace distutils.util.strtobool
- Enabled Python 3.12 for tests
- Add fedora-39 image
- Remove duplicate protocol from Homepage URL
- Update Readme installation instructions for Debian to use pip

# 2.3.1

- Renamed Tox env name in GH Actions job
- README: explain how to install the dep to build the Python binding
- clean up ruff errors, convert string.format calls to f-strings (#279)
- remove debian-testing image, link nolonger exists, and was based on debian-10 add debian-12 image add debian-sid
- Update README with snapshots example
- Add fixes fo fstrings
- Change default "meta_data_media_type" to "cdrom"
- refresh the BSD and Amazon images

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
