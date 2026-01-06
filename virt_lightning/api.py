#!/usr/bin/env python3

import asyncio
import collections
import ipaddress
import json
import logging
import lzma
import pathlib
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import libvirt
import yaml

import virt_lightning.virt_lightning as vl
from virt_lightning.configuration import Configuration
from virt_lightning.symbols import get_symbols
from virt_lightning.util import strtobool

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
    try:
        loop = loop or asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    if loop not in _register_aio_virt_impl.aio_virt_bindinds:
        try:
            import libvirtaio

            libvirtaio.virEventRegisterAsyncIOImpl(loop=loop)
        except ImportError:
            libvirt.virEventRegisterDefaultImpl()
        _register_aio_virt_impl.aio_virt_bindinds[loop] = True
    return loop


_register_aio_virt_impl.__dict__["aio_virt_bindinds"] = {}


def _connect_libvirt(uri):
    try:
        return libvirt.open(uri)
    except libvirt.libvirtError as e:
        if e.get_error_code() == libvirt.VIR_ERR_AUTH_UNAVAILABLE:
            raise CannotConnectToLibvirtError() from None
        raise


def _start_domain(hv, host, context, configuration):
    distro = host["distro"]
    if "name" not in host:
        host["name"] = re.sub(r"[^a-zA-Z0-9-]+", "", distro)

    domain = hv.get_domain_by_name(host["name"])
    if not domain:
        pass
    elif domain.dom.isActive():
        logger.info(f"Skipping {host['name']}, already here.")
        return
    else:
        logger.info(f"Skipping {host['name']}, already here but is not running.")
        logger.info(
            f"You can restart it with: virsh -c qemu:///system start {host['name']}"
        )
        logger.info(f"You can also destroy the instance with: vl stop {host['name']}")
        raise VMNotRunningError(host["name"])

    logger.info(f"{symbols.LIGHTNING.value} {host['name']} ")

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
                raise ImageNotFoundLocallyError(distro) from None


def up(virt_lightning_yaml, configuration, context="default", **kwargs):
    """Create a list of VM."""

    def _lifecycle_callback(conn, dom, state, reason, opaque):  # noqa: N802
        if state == 1:
            logger.info("%s %s QEMU agent found", symbols.CUSTOMS.value, dom.name())

    loop = _register_aio_virt_impl(kwargs.get("loop"))

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
    """Start a single VM."""
    conn = _connect_libvirt(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)
    hv.init_network(configuration.network_name, configuration.network_cidr)
    hv.init_storage_pool(configuration.storage_pool)
    host = {
        k: kwargs[k] for k in ["name", "distro", "memory", "vcpus"] if kwargs.get(k)
    }
    if kwargs.get("disk"):
        host.update({"disks": [{"size": x} for x in kwargs["disk"]]})
    _ensure_image_exists(hv, [host])
    domain = _start_domain(hv, host, context, configuration)
    if not domain:
        return

    loop = _register_aio_virt_impl(loop=kwargs.get("loop"))

    if enable_console:
        import time

        if console_fd is None:
            console_fd = sys.stdout

        time.sleep(4)
        stream = conn.newStream(libvirt.VIR_STREAM_NONBLOCK)
        console = domain.dom.openConsole(None, stream, 0)

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
    """Stop and delete a given VM."""
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
    """Generate an Ansible inventory based on the running VM."""
    conn = _connect_libvirt(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)

    ssh_cmd_template = (
        "{name} ansible_host={ipv4} ansible_user={username} "
        "{additional_nics}"
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
            additional_nics=domain.additional_nics or "",
            python_interpreter=domain.python_interpreter,
        )  # noqa: T001

    for group_name, domains in groups.items():
        output += f"\n[{group_name}]\n"
        for domain in domains:
            output += domain.name + "\n"
    return output


def ssh_config(configuration, context="default", **kwargs):
    """Generate an SSH configuration based on the running VM."""
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
        output += f"\n[{group_name}]"
        for domain in domains:
            output += domain.name
    return output


def status(configuration, context="default", name=None, **kwargs):
    """Returns the status of the VM of the envionment."""
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
    """Open an SSH connection on a host."""
    conn = _connect_libvirt(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)
    domain = hv.get_domain_by_name(name)
    if not domain:
        raise VMNotFoundError(name)
    domain.exec_ssh()


def list_domains(configuration, name=None, **kwargs):
    """Return a list Python-libvirt instance of the running libvirt VM."""
    conn = _connect_libvirt(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)
    return sorted(hv.list_domains())


def down(configuration, context="default", **kwargs):
    """Stop and remove a running environment."""
    conn = _connect_libvirt(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)
    hv.init_network(configuration.network_name, configuration.network_cidr)
    hv.init_storage_pool(configuration.storage_pool)
    for domain in hv.list_domains():
        if domain.context != context:
            continue
        logger.info("%s purging %s", symbols.TRASHBIN.value, domain.name)
        hv.clean_up(domain)

    if strtobool(configuration.network_auto_clean_up):
        hv.network_obj.destroy()


def images(configuration, **kwargs):
    """Return a list of VM images that are available on the system."""
    conn = _connect_libvirt(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)
    hv.init_storage_pool(configuration.storage_pool)
    return hv.distro_available()


def list_remote_images(configuration, **kwargs):
    """Fetch images.json from the configured URL and return a list of available images."""
    try:
        image_index = get_image_index(configuration)
        return [image["name"] for image in image_index]
    except Exception as e:
        logger.error(f"Failed to fetch images.json: {e}")
        raise


def storage_dir(configuration, **kwargs):
    """Return the location of the VM image storage directory."""
    conn = _connect_libvirt(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)
    hv.init_storage_pool(configuration.storage_pool)
    return hv.get_storage_dir()


class RedirectFilter(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        logger.info("downloading image from: %s", newurl)
        return urllib.request.HTTPRedirectHandler.redirect_request(
            self, req, fp, code, msg, hdrs, newurl
        )


def fetch_distro(
    configuration, progress_callback=None, storage_dir=None, custom_url=None, **kwargs
):
    """Unified function to retrieve a VM image from custom URL or distro index."""
    target_file = pathlib.PosixPath(f"{storage_dir}/upstream/{kwargs['distro']}.qcow2")
    temp_file = target_file.with_suffix(".temp")
    if target_file.exists():
        logger.info("File already exists: %s", target_file)
        return

    opener = urllib.request.build_opener(RedirectFilter)
    urllib.request.install_opener(opener)


    def get_image_info():
        # Try private hub first, then distro index
        for images_url in configuration.private_hub:
            try:
                download_url = f"{images_url}/{kwargs['distro']}.qcow2"
                urllib.request.urlopen(download_url)
                return {"qcow2_url": download_url}
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    logger.info(
                        "Image: %s not found from url: %s", kwargs["distro"], images_url
                    )
                    continue
                raise
        else:
            # Try from distro index
            image_index = get_image_index(configuration)
            try:
                image_info = [i for i in image_index if i["name"] == kwargs["distro"]][
                    0
                ]
                return image_info
            except (IndexError, KeyError):
                raise ImageNotFoundUpstreamError(kwargs["distro"]) from None

    image_info = {} if custom_url else get_image_info()
    download_url = custom_url or image_info["qcow2_url"]


    # Open the URL if not already opened
    try:
        r = urllib.request.urlopen(download_url)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ImageNotFoundUpstreamError(kwargs["distro"]) from None
        raise

    last_modified = r.headers.get("Last-Modified", "unknown")
    logger.debug("Date: %s", last_modified)

    # Check if content is xz-compressed
    content_type = r.headers.get("Content-Type", "")
    is_xz_compressed = (
        content_type.lower() == "application/x-xz" or download_url.endswith(".xz")
    )

    if is_xz_compressed:
        logger.info("Detected xz-compressed content, decompressing during download...")
        # Wrap the response in an LZMA decompressor
        response_stream = lzma.LZMAFile(r, "rb")  # noqa: SIM115
        length = None
    else:
        response_stream = r
        length = int(r.headers.get("Content-Length", 0))
        logger.debug("Size: %s", length)

    chunk_size = MB * 1
    bytes_downloaded = 0
    with temp_file.open("wb") as fd:
        while chunk := response_stream.read(chunk_size):
            fd.write(chunk)
            bytes_downloaded += len(chunk)
            if progress_callback:
                progress_callback(bytes_downloaded, length)

    temp_file.rename(target_file)

    # Handle YAML file for distro index downloads (if not custom URL)
    if image_info.get("meta"):
        try:
            with target_file.with_suffix(".yaml").open("wb") as fd:
                meta = yaml.dump(image_info.get("meta"))
                fd.write(meta.encode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                pass

    logger.info(f"Image {kwargs['distro']} is ready!")


def get_image_index(configuration):

    image_list = configuration.custom_image_list
    if not image_list:
        image_list = (
            "https://raw.githubusercontent.com/virt-lightning/virt-lightning"
            "/refs/heads/main/virt-lightning.org/images.json"
        )
    logger.info(f"Fetching images.json from: {image_list}")
    f = urllib.request.urlopen(image_list)
    return json.loads(f.read())


def fetch(configuration=None, progress_callback=None, hv=None, **kwargs):
    """Retrieve a VM image from Internet."""
    if hv is None:
        conn = _connect_libvirt(configuration.libvirt_uri)
        hv = vl.LibvirtHypervisor(conn)
        hv.init_storage_pool(configuration.storage_pool)

    configuration = configuration if configuration is not None else Configuration()

    distro = kwargs.get("distro")
    custom_url = kwargs.get("url")

    # Ensure distro is always provided
    if not distro:
        raise ValueError("Distro name is required")

    fetch_distro(
        configuration=configuration,
        progress_callback=progress_callback,
        storage_dir=hv.get_storage_dir(),
        custom_url=custom_url,
        **kwargs,
    )
