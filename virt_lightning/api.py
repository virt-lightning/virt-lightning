#!/usr/bin/env python3

import collections
from concurrent.futures import ThreadPoolExecutor
import logging

import asyncio
import ipaddress
import libvirt
import re
import pathlib

import urllib.request
import sys
import distutils.util
from virt_lightning.symbols import get_symbols
from virt_lightning.configuration import Configuration

import virt_lightning.virt_lightning as vl

BASE_URL = "https://virt-lightning.org"

logger = logging.getLogger("virt_lightning")


def libvirt_callback(userdata, err):
    pass


libvirt.registerErrorHandler(f=libvirt_callback, ctx=None)
symbols = get_symbols()

MB = 1024 * 1000


class VMNotFoundError(Exception):
    def __init__(self, name):
        self.name = name


class VMNotRunningError(Exception):
    def __init__(self, name):
        self.name = name


class ImageNotFoundUpstreamError(Exception):
    def __init__(self, name):
        self.name = name


class ImageNotFoundLocallyError(Exception):
    def __init__(self, name):
        self.name = name


class CannotConnectToLibvirtError(Exception):
    pass


def _register_aio_virt_impl(loop):
    # Ensure we may call shell.up() multiple times
    # from the same asyncio program.
    loop = loop or asyncio.get_event_loop()
    if loop not in _register_aio_virt_impl.aio_virt_bindinds:
        try:
            import libvirtaio

            libvirtaio.virEventRegisterAsyncIOImpl(loop=loop)
        except ImportError:
            libvirt.virEventRegisterDefaultImpl()
        _register_aio_virt_impl.aio_virt_bindinds[loop] = True


_register_aio_virt_impl.__dict__["aio_virt_bindinds"] = {}


def _connect_libvirt(uri):
    try:
        return libvirt.open(uri)
    except libvirt.libvirtError as e:
        if e.get_error_code() == libvirt.VIR_ERR_AUTH_UNAVAILABLE:
            raise CannotConnectToLibvirtError()
        raise


def _start_domain(hv, host, context, configuration):
    distro = host["distro"]
    if "name" not in host:
        host["name"] = re.sub(r"[^a-zA-Z0-9-]+", "", distro)

    domain = hv.get_domain_by_name(host["name"])
    if not domain:
        pass
    elif domain.dom.isActive():
        logger.info("Skipping {name}, already here.".format(**host))
        return
    else:
        logger.info(f"Skipping {host['name']}, already here but is not running.")
        logger.info(
            f"You can restart it with: virsh -c qemu:///system start {host['name']}"
        )
        logger.info(f"You can also destroy the instance with: vl stop {host['name']}")
        raise VMNotRunningError(host["name"])

    # Unfortunatly, i can't decode that symbol
    # that symbol more well add to check encoding block
    logger.info("{lightning} {name} ".format(lightning=symbols.LIGHTNING.value, **host))

    user_config = {
        "groups": host.get("groups"),
        "memory": host.get("memory"),
        "python_interpreter": host.get("python_interpreter"),
        "root_password": host.get("root_password", configuration.root_password),
        "ssh_key_file": host.get("ssh_key_file", configuration.ssh_key_file),
        "username": host.get("username"),
        "vcpus": host.get("vcpus"),
        "fqdn": host.get("fqdn"),
        "default_nic_mode": host.get("default_nic_model"),
        "bootcmd": host.get("bootcmd"),
        "runcmd": host.get("runcmd"),
        "meta_data_media_type": host.get("meta_data_media_type"),
        "default_bus_type": host.get("default_bus_type"),
    }
    domain = hv.create_domain(name=host["name"], distro=distro)
    hv.configure_domain(domain, user_config)
    domain.context = context
    networks = host.get("networks", [{}])
    for i, network in enumerate(networks):
        if "network" not in network:
            network["network"] = configuration.network_name
        if i == 0 and not network.get("ipv4"):
            network["ipv4"] = hv.get_free_ipv4()
        ipv4 = network.get("ipv4")
        if ipv4:
            network["mac"] = hv.reuse_mac_address(
                network["network"], host["name"], ipaddress.ip_interface(ipv4)
            )
        domain.attach_network(**network)

    if "root_disk_size" in host:
        logger.debug("The key 'root_disk_size' is deprecated. Use 'disks' instead")

    disks = host.get("disks", [{"size": 15}])
    for i, disk in enumerate(disks):
        size = 1
        if "size" in disk:
            size = int(disk["size"])

        # Old behavior
        if "disks" not in host and "root_disk_size" in host:
            size = int(host["root_disk_size"])

        volume = hv.create_disk(
            name=f"{host['name']}-{i}", backing_on=(distro if i == 0 else ""), size=size
        )
        domain.attach_disk(volume=volume)

    hv.start(domain, metadata_format=host.get("metadata_format", {}))
    return domain


def _ensure_image_exists(hv, hosts):
    for host in hosts:
        distro = host.get("distro")
        if distro not in hv.distro_available():
            logger.debug("distro not available: %s, will be fetched", distro)
            try:
                fetch(hv=hv, distro=distro)
            except ImageNotFoundUpstreamError:
                raise ImageNotFoundLocallyError(distro)


def up(virt_lightning_yaml, configuration, context="default", **kwargs):
    """
    Create a list of VM
    """

    def _lifecycle_callback(conn, dom, state, reason, opaque):  # noqa: N802
        if state == 1:
            logger.info("%s %s QEMU agent found", symbols.CUSTOMS.value, dom.name())

    loop = kwargs.get("loop") or asyncio.get_event_loop()
    _register_aio_virt_impl(loop)

    conn = _connect_libvirt(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)

    hv.init_network(configuration.network_name, configuration.network_cidr)
    hv.init_storage_pool(configuration.storage_pool)

    _ensure_image_exists(hv, virt_lightning_yaml)
    conn = _connect_libvirt(configuration.libvirt_uri)
    conn.setKeepAlive(interval=5, count=3)
    conn.domainEventRegisterAny(
        None,
        libvirt.VIR_DOMAIN_EVENT_ID_AGENT_LIFECYCLE,
        _lifecycle_callback,
        None,
    )

    pool = ThreadPoolExecutor(max_workers=10)

    async def deploy():
        futures = []
        for host in virt_lightning_yaml:
            futures.append(
                loop.run_in_executor(
                    pool, _start_domain, hv, host, context, configuration
                )
            )

        domain_reachable_futures = []
        for f in futures:
            await f
            domain = f.result()
            if domain:
                domain_reachable_futures.append(domain.reachable())
        logger.info("%s ok Waiting...", symbols.HOURGLASS.value)

        await asyncio.gather(*domain_reachable_futures)

    loop.run_until_complete(deploy())
    logger.info("%s You are all set", symbols.THUMBS_UP.value)


def start(
    configuration, context="default", enable_console=False, console_fd=None, **kwargs
):
    """
    Start a single VM
    """
    conn = _connect_libvirt(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)
    hv.init_network(configuration.network_name, configuration.network_cidr)
    hv.init_storage_pool(configuration.storage_pool)
    host = {
        k: kwargs[k] for k in ["name", "distro", "memory", "vcpus"] if kwargs.get(k)
    }
    _ensure_image_exists(hv, [host])
    domain = _start_domain(hv, host, context, configuration)
    if not domain:
        return

    loop = kwargs.get("loop") or asyncio.get_event_loop()

    if enable_console:
        import time

        if console_fd is None:
            console_fd = sys.stdout

        time.sleep(4)
        stream = conn.newStream(libvirt.VIR_STREAM_NONBLOCK)
        console = domain.dom.openConsole(None, stream, 0)

        _register_aio_virt_impl(loop=kwargs.get("loop"))

        def stream_callback(stream, events, _):
            content = stream.recv(1024 * 1024).decode("utf-8", errors="ignore")
            console_fd.write(content)

        stream.eventAddCallback(
            libvirt.VIR_STREAM_EVENT_READABLE, stream_callback, console
        )

    async def deploy():
        await domain.reachable()

    loop.run_until_complete(deploy())
    logger.info(  # noqa: T001
        (
            "\033[0m\n**** System is online ****\n"
            "To connect use:\n"
            "  vl console %s (virsh console)"
            "  vl ssh %s"
        ),
        domain.name,
        domain.name,
    )
    return domain


def stop(configuration, **kwargs):
    """
    Stop and delete a given VM
    """
    conn = _connect_libvirt(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)
    hv.init_network(configuration.network_name, configuration.network_cidr)
    hv.init_storage_pool(configuration.storage_pool)
    domain = hv.get_domain_by_name(kwargs["name"])
    if not domain:
        vm_list = [d.name for d in hv.list_domains()]
        if vm_list:
            logger.info(
                "No VM called %s in: %s", kwargs.get("name"), ", ".join(vm_list)
            )
        else:
            logger.info("No running VM.")
        raise VMNotFoundError(kwargs["name"])
    hv.clean_up(domain)


def ansible_inventory(configuration, context="default", **kwargs):
    """
    Generate an Ansible inventory based on the running VM
    """
    conn = _connect_libvirt(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)

    ssh_cmd_template = (
        "{name} ansible_host={ipv4} ansible_user={username} "
        "ansible_python_interpreter={python_interpreter} "
        'ansible_ssh_common_args="-o UserKnownHostsFile=/dev/null '
        "-o GSSAPIAuthentication=no -o GSSAPIKeyExchange=no "
        '-o StrictHostKeyChecking=no"\n'
    )

    output = ""
    groups = collections.defaultdict(list)
    for domain in hv.list_domains():
        if domain.context != context:
            continue

        for group in domain.groups:
            groups[group].append(domain)

        template = ssh_cmd_template

        output += template.format(
            name=domain.name,
            username=domain.username,
            ipv4=domain.ipv4.ip,
            python_interpreter=domain.python_interpreter,
        )  # noqa: T001

    for group_name, domains in groups.items():
        output += "\n[{group_name}]\n".format(group_name=group_name)
        for domain in domains:
            output += domain.name + "\n"
    return output


def ssh_config(configuration, context="default", **kwargs):
    """
    Generate an SSH configuration based on the running VM
    """
    conn = _connect_libvirt(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)

    ssh_host_template = (
        "Host {name}\n"
        "     Hostname {ipv4}\n"
        "     User {username}\n"
        "     IdentityFile {ssh_key_file}\n"
    )

    output = ""
    groups = {}
    for domain in hv.list_domains():
        for group in domain.groups:
            groups[group].append(domain)

        if domain.context != context:
            continue

        template = ssh_host_template

        output += template.format(
            name=domain.name,
            username=domain.username,
            ipv4=domain.ipv4.ip,
            ssh_key_file=domain.ssh_key,
        )

    for group_name, domains in groups.items():
        output += "\n[{group_name}]".format(group_name=group_name)
        for domain in domains:
            output += domain.name
    return output


def status(configuration, context="default", name=None, **kwargs):
    """
    Returns the status of the VM of the envionment
    """
    conn = _connect_libvirt(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)

    for domain in hv.list_domains():
        if context and context != domain.context:
            continue
        name = domain.name
        if not domain.ipv4:  # Not a VL managed VM
            continue
        yield {
            "name": name,
            "ipv4": domain.ipv4 and str(domain.ipv4.ip),
            "context": domain.context,
            "username": domain.username,
            "distro": domain.distro,
        }


def exec_ssh(configuration, name=None, **kwargs):
    """
    Open an SSH connection on a host
    """
    conn = _connect_libvirt(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)
    domain = hv.get_domain_by_name(name)
    if not domain:
        raise VMNotFoundError(name)
    domain.exec_ssh()


def list_domains(configuration, name=None, **kwargs):
    """
    Return a list Python-libvirt instance of the running libvirt VM.
    """
    conn = _connect_libvirt(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)
    return sorted(hv.list_domains())


def down(configuration, context="default", **kwargs):
    """
    Stop and remove a running environment.
    """
    conn = _connect_libvirt(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)
    hv.init_network(configuration.network_name, configuration.network_cidr)
    hv.init_storage_pool(configuration.storage_pool)
    for domain in hv.list_domains():
        if domain.context != context:
            continue
        logger.info("%s purging %s", symbols.TRASHBIN.value, domain.name)
        hv.clean_up(domain)

    if bool(distutils.util.strtobool(configuration.network_auto_clean_up)):
        hv.network_obj.destroy()


def distro_list(configuration, **kwargs):
    """
    Return a list of VM images that are available on the system.
    """
    conn = _connect_libvirt(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)
    hv.init_storage_pool(configuration.storage_pool)
    return hv.distro_available()


def storage_dir(configuration, **kwargs):
    """
    Return the location of the VM image storage directory.
    """
    conn = _connect_libvirt(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)
    hv.init_storage_pool(configuration.storage_pool)
    return hv.get_storage_dir()


def fetch_from_url(progress_callback=None, url=None, **kwargs):
    """
    Retrieve a VM image from a given url
        - when url is set to None, this means we are trying to fetch from the default url
    """

    target_file = pathlib.PosixPath(
        "{storage_dir}/upstream/{distro}.qcow2".format(**kwargs)
    )
    temp_file = target_file.with_suffix(".temp")
    if target_file.exists():
        logger.info("File already exists: %s", target_file)
        return

    class RedirectFilter(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, hdrs, newurl):
            logger.info("downloading image from: %s", newurl)
            return urllib.request.HTTPRedirectHandler.redirect_request(
                self, req, fp, code, msg, hdrs, newurl
            )

    opener = urllib.request.build_opener(RedirectFilter)
    urllib.request.install_opener(opener)

    parent_url = BASE_URL + "/images/{distro}".format(**kwargs) if url is None else url
    try:
        r = urllib.request.urlopen(
            "{url}/{distro}.qcow2".format(url=parent_url, **kwargs)
        )
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ImageNotFoundUpstreamError(kwargs["distro"])
        else:
            logger.exception(e)
            raise
    last_modified = r.headers["Last-Modified"]
    logger.debug("Date: %s", last_modified)
    size = r.headers["Content-Length"]
    logger.debug("Size: %s", size)
    length = int(size)
    chunk_size = MB * 1
    with temp_file.open("wb") as fd:
        while fd.tell() < length:
            chunk = r.read(chunk_size)
            fd.write(chunk)
            if progress_callback:
                progress_callback(fd.tell(), length)
    temp_file.rename(target_file)
    try:
        r = urllib.request.urlopen(
            "{url}/{distro}.yaml".format(url=parent_url, **kwargs)
        )
    except urllib.error.HTTPError as e:
        if e.code == 404:
            pass
    with target_file.with_suffix(".yaml").open("wb") as fd:
        fd.write(r.read())
    logger.info("Image {distro} is ready!".format(**kwargs))


def fetch(configuration=None, progress_callback=None, hv=None, **kwargs):
    """
    Retrieve a VM image from Internet.
    """
    if hv is None:
        conn = _connect_libvirt(configuration.libvirt_uri)
        hv = vl.LibvirtHypervisor(conn)
        hv.init_storage_pool(configuration.storage_pool)

    configuration = configuration if configuration is not None else Configuration()
    image_found = False
    for images_url in configuration.private_hub:
        try:
            fetch_from_url(
                progress_callback=progress_callback,
                storage_dir=hv.get_storage_dir(),
                url=images_url,
                **kwargs,
            )
            image_found = True
            break
        except ImageNotFoundUpstreamError:
            logger.info(
                "Image: %s not found from url: %s", kwargs["distro"], images_url
            )

    if not image_found:
        # image not found from custom url
        # fetch from base url
        fetch_from_url(
            progress_callback=progress_callback,
            storage_dir=hv.get_storage_dir(),
            **kwargs,
        )
