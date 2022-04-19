DISK_XML = """
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source />
      <target bus='virtio'/>
    </disk>
"""

DOMAIN_XML = """
<domain type='kvm'>
  <name></name>
  <memory unit='KiB'>786432</memory>
  <currentMemory unit='KiB'>786432</currentMemory>
  <vcpu>2</vcpu>
  <os>
    <type arch='x86_64' machine='pc'>hvm</type>
    <boot dev='hd'/>
  </os>
  <features>
    <acpi/>
    <apic/>
    <vmport state='off'/>
  </features>
  <cpu mode='host-model' check='partial'>
    <model fallback='allow'/>
  </cpu>
  <clock offset='utc'>
    <timer name='rtc' tickpolicy='catchup'/>
    <timer name='pit' tickpolicy='delay'/>
    <timer name='hpet' present='no'/>
  </clock>
  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>destroy</on_crash>
  <pm>
    <suspend-to-mem enabled='no'/>
    <suspend-to-disk enabled='no'/>
  </pm>
  <devices>
    <emulator>/usr/bin/qemu-kvm</emulator>
    <controller type='usb'></controller>
    <controller type='pci' model='pci-root'/>
    <console type='pty'>
      <target type='serial'/>
    </console>
    <console type='pty'>
      <target type='virtio'/>
    </console>
    <channel type='unix'>
      <target type='virtio' name='org.qemu.guest_agent.0' state='connected'/>
    </channel>
    <input type='mouse' bus='ps2'/>
    <input type='keyboard' bus='ps2'/>
    <graphics type="vnc" port="-1" autoport="yes" listen="127.0.0.1" keymap="en-us">
      <listen type="address" address="127.0.0.1"/>
    </graphics>
    <memballoon model='virtio'></memballoon>
  </devices>
</domain>
"""  # NOQA

BRIDGE_XML = """
<interface type='network'>
  <source network='virt-lightning'/>
  <model type='virtio'/>
</interface>
"""

NETWORK_XML = """
<network>
  <name></name>
  <forward mode='nat'/>
  <bridge name='virbr0' stp='off' delay='0'/>
  <ip address='192.168.123.1' netmask='255.255.255.0'>
  <dhcp>
    <leasetime>10s</leasetime>
  </dhcp>
  </ip>
</network>
"""

NETWORK_HOST_ENTRY = """
<host ip="">
</host>"""

NETWORK_DHCP_ENTRY = """
<host />
"""

# TODO
META_DATA_ENI = """
dsmode: local
instance-id: iid-{name}
local-hostname: {name}
network-interfaces: |
   iface eth0 inet static
   address {ipv4}
   network {network}
   netmask 255.255.255.0
   gateway {gateway}
"""

STORAGE_POOL_XML = """
<pool type='dir'>
  <name></name>
  <source>
  </source>
  <target>
    <path></path>
  </target>
</pool>
"""

STORAGE_VOLUME_XML = """
<volume>
  <name></name>
  <allocation>0</allocation>
  <capacity unit="G">1</capacity>
  <target>
    <format type='qcow2'/>
    <path></path>
  </target>
</volume>
"""

USER_CREATE_STORAGE_POOL_DIR = """
You need root privilege to create the storage pool, please do:
  sudo mkdir -p {storage_dir}/upstream
  sudo chown -R {qemu_user}:{qemu_group} {storage_dir}
  sudo chown -R {user} {storage_dir}/upstream
  sudo chmod 775 /var/lib/virt-lightning
  sudo chmod 775 {storage_dir} {storage_dir}/upstream
"""
