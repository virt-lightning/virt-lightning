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
    <controller type='usb' index='0' model='ich9-ehci1'>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x05' function='0x7'/>
    </controller>
    <controller type='usb' index='0' model='ich9-uhci1'>
      <master startport='0'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x05' function='0x0' multifunction='on'/>
    </controller>
    <controller type='usb' index='0' model='ich9-uhci2'>
      <master startport='2'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x05' function='0x1'/>
    </controller>
    <controller type='usb' index='0' model='ich9-uhci3'>
      <master startport='4'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x05' function='0x2'/>
    </controller>
    <controller type='pci' index='0' model='pci-root'/>
    <controller type='ide' index='0'>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x01' function='0x1'/>
    </controller>
    <serial type='pty'>
      <target type='isa-serial' port='0'>
        <model name='isa-serial'/>
      </target>
    </serial>
    <console type='pty'>
      <target type='serial' port='0'/>
    </console>
    <channel type='unix'>
      <target type='virtio' name='org.qemu.guest_agent.0'/>
      <address type='virtio-serial' controller='0' bus='0' port='1'/>
    </channel>
    <channel type='spicevmc'>
      <target type='virtio' name='com.redhat.spice.0'/>
      <address type='virtio-serial' controller='0' bus='0' port='2'/>
    </channel>
    <input type='tablet' bus='usb'>
      <address type='usb' bus='0' port='1'/>
    </input>
    <input type='mouse' bus='ps2'/>
    <input type='keyboard' bus='ps2'/>
    <graphics type='spice' autoport='yes'>
      <listen type='address'/>
      <image compression='off'/>
    </graphics>
    <sound model='ich6'>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x04' function='0x0'/>
    </sound>
    <video>
      <model type='qxl' ram='65536' vram='65536' vgamem='16384' heads='1' primary='yes'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x02' function='0x0'/>
    </video>
    <redirdev bus='usb' type='spicevmc'>
      <address type='usb' bus='0' port='2'/>
    </redirdev>
    <redirdev bus='usb' type='spicevmc'>
      <address type='usb' bus='0' port='3'/>
    </redirdev>
    <memballoon model='virtio'>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x06' function='0x0'/>
    </memballoon>
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
  sudo chmod 775 /var/lib/virt-lightning
  sudo chmod 775 {storage_dir} {storage_dir}/upstream
"""
