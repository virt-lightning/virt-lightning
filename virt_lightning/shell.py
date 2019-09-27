#!/usr/bin/env python3

from concurrent.futures import ThreadPoolExecutor
import argparse
import asyncio
import logging
import os
import pathlib
import re

import libvirt
import yaml

from virt_lightning.configuration import Configuration
from virt_lightning.symbols import get_symbols
import virt_lightning.ui as ui
import virt_lightning.virt_lightning as vl

symbols = get_symbols()
logger = logging.getLogger("virt_lightning")
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
logger.addHandler(ch)


def libvirt_callback(userdata, err):
    pass


libvirt.registerErrorHandler(f=libvirt_callback, ctx=None)


def _start_domain(hv, host, context, configuration):
    if host["distro"] not in hv.distro_available():
        logger.error("distro not available: %s", host["distro"])
        logger.info(
            "Please select on of the following distro: %s", hv.distro_available()
        )
        exit()

    if "name" not in host:
        host["name"] = re.sub(r"\W+", "", host["distro"])

    if hv.get_domain_by_name(host["name"]):
        logger.info("Skipping {name}, already here.".format(**host))
        return

    # Unfortunatly, i can't decode that symbol
    # that symbol more well add to check encoding block
    logger.info("{lightning} {name} ".format(lightning=symbols.LIGHTNING.value, **host))
    domain = hv.create_domain(name=host["name"], distro=host["distro"])
    domain.context = context
    domain.groups = host.get("groups", [])
    domain.load_ssh_key_file(configuration.ssh_key_file)
    if host["distro"].startswith("esxi"):
        domain.username = "root"
    else:
        domain.username = configuration.username
    domain.root_password = host.get("root_password", configuration.root_password)

    domain.vcpus(host.get("vcpus", 1))
    domain.memory(host.get("memory", 768))
    root_disk_path = hv.create_disk(
        name=host["name"],
        backing_on=host["distro"],
        # NOTE: Use to be 15GB, but FreeBSD root FS is 31G large
        size=host.get("root_disk_size", 32),
    )
    domain.add_root_disk(root_disk_path)
    domain.attachNetwork(configuration.network_name)
    domain.ipv4 = hv.get_free_ipv4()
    domain.add_swap_disk(hv.create_disk(host["name"] + "-swap", size=1))
    hv.start(domain)
    return domain


def up(virt_lightning_yaml, configuration, context, **kwargs):
    def myDomainEventAgentLifecycleCallback(conn, dom, state, reason, opaque):
        if state == 1:
            logger.info("%s %s QEMU agent found", symbols.CUSTOMS.value, dom.name())

    loop = asyncio.get_event_loop()
    try:
        import libvirtaio

        libvirtaio.virEventRegisterAsyncIOImpl(loop=loop)
    except ImportError:
        libvirt.virEventRegisterDefaultImpl()
        pass
    conn = libvirt.open(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)

    conn.setKeepAlive(5, 3)
    conn.domainEventRegisterAny(
        None,
        libvirt.VIR_DOMAIN_EVENT_ID_AGENT_LIFECYCLE,
        myDomainEventAgentLifecycleCallback,
        None,
    )

    hv.init_network(configuration.network_name, configuration.network_cidr)
    hv.init_storage_pool(configuration.storage_pool)

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


def start(configuration, **kwargs):
    conn = libvirt.open(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)
    hv.init_network(configuration.network_name, configuration.network_cidr)
    hv.init_storage_pool(configuration.storage_pool)
    host = {"distro": kwargs["distro"]}
    context = "default"
    domain = _start_domain(hv, host, context, configuration)
    if not domain:
        return
    import time

    time.sleep(4)
    stream = conn.newStream(libvirt.VIR_STREAM_NONBLOCK)
    console = domain.dom.openConsole(None, stream, 0)
    loop = asyncio.get_event_loop()
    import libvirtaio

    libvirtaio.virEventRegisterAsyncIOImpl(loop=loop)

    def stream_callback(stream, events, _):
        line = stream.recv(1024).decode()
        print("\033[0m", "\033[30m", line, end="")

    stream.eventAddCallback(libvirt.VIR_STREAM_EVENT_READABLE, stream_callback, console)

    async def deploy():
        await domain.reachable()

    loop.run_until_complete(deploy())
    print(
        (
            "\033[0m\n**** System is online ****\n"
            "To connect use:\n"
            "  vl console {name} (virsh console)"
            "  vl ssh {name}"
        ).format(name=domain.name)
    )
    if kwargs["ssh"]:
        domain.exec_ssh()


def stop(configuration, **kwargs):
    conn = libvirt.open(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)
    hv.init_network(configuration.network_name, configuration.network_cidr)
    hv.init_storage_pool(configuration.storage_pool)
    domain = hv.get_domain_by_name(kwargs["name"])
    if not domain:
        vm_list = [d.name for d in hv.list_domains()]
        print(
            "No VM called {name} in {vm_list}".format(
                name=kwargs["name"], vm_list=vm_list
            )
        )
        exit(1)
    hv.clean_up(domain)


def ansible_inventory(configuration, context, **kwargs):
    conn = libvirt.open(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)

    ssh_cmd_template = (
        "{name} ansible_host={ipv4} ansible_user={username} "
        'ansible_ssh_common_args="-o UserKnownHostsFile=/dev/null '
        '-o StrictHostKeyChecking=no"'
    )
    ssh_cmd_template_esxi = (
        "{name} ansible_host={ipv4} ansible_user=root "
        "ansible_password=root ansible_python_interpreter=/bin/python "
        'ansible_ssh_common_args="-o UserKnownHostsFile=/dev/null '
        '-o StrictHostKeyChecking=no"'
    )

    groups = {}
    for domain in hv.list_domains():
        for group in domain.groups:
            if group not in groups:
                groups[group] = []
            groups[group].append(domain)

        if domain.context != context:
            continue

        if domain.distro.startswith("esxi"):
            template = ssh_cmd_template_esxi
        else:
            template = ssh_cmd_template

        print(
            template.format(
                name=domain.name, username=domain.username, ipv4=domain.ipv4.ip
            )
        )  # noqa: T001

    for group_name, domains in groups.items():
        print("")
        print("[{group_name}]".format(group_name=group_name))
        for domain in domains:
            print(domain.name)


def get_status(hv, context):
    status = []
    for domain in hv.list_domains():
        if context and context != domain.context:
            continue
        name = domain.name
        status.append(
            {
                "name": name,
                "ipv4": str(domain.ipv4.ip),
                "context": domain.context,
                "username": domain.username,
            }
        )
    return status


def status(configuration, context=None, **kwargs):
    conn = libvirt.open(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)
    results = {}

    def iconify(v):
        if isinstance(v, str):
            return v
        elif v:
            return symbols.CHECKMARK.value
        else:
            return symbols.CROSS.value

    for status in get_status(hv, context):
        results[status["name"]] = {
            "name": status["name"],
            "ipv4": status["ipv4"] or "waiting",
            "context": status["context"],
            "username": status["username"],
        }

    output_template = "{computer} {name:<13}   {arrow}   {username}@{ipv4:>5}"
    for _, v in sorted(results.items()):
        print(  # noqa: T001
            output_template.format(
                computer=symbols.COMPUTER.value, arrow=symbols.RIGHT_ARROW.value, **v
            )
        )


def ssh(configuration, name=None, **kwargs):
    conn = libvirt.open(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)

    def go_ssh(domain):
        domain.exec_ssh()

    if name:
        hv.get_domain_by_name(name).exec_ssh()

    ui.Selector(sorted(hv.list_domains()), go_ssh)


def console(configuration, name=None, **kwargs):
    conn = libvirt.open(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)

    def go_console(domain):
        os.execlp(
            "virsh", "virsh", "-c", configuration.libvirt_uri, "console", domain.name
        )

    if name:
        go_console(hv.get_domain_by_name(name))

    ui.Selector(sorted(hv.list_domains()), go_console)


def down(configuration, context, **kwargs):
    conn = libvirt.open(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)
    hv.init_network(configuration.network_name, configuration.network_cidr)
    hv.init_storage_pool(configuration.storage_pool)
    for domain in hv.list_domains():
        if context and domain.context != context:
            continue
        logger.info("%s purging %s", symbols.TRASHBIN.value, domain.name)
        hv.clean_up(domain)


def distro_list(configuration, **kwargs):
    conn = libvirt.open(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)
    hv.init_storage_pool(configuration.storage_pool)
    for distro in hv.distro_available():
        print("- distro: {distro}".format(distro=distro))  # noqa: T001


def storage_dir(configuration, **kwargs):
    conn = libvirt.open(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)
    hv.init_storage_pool(configuration.storage_pool)
    print(hv.get_storage_dir())  # noqa: T001


def main():

    title = "{lightning} Virt-Lightning {lightning}".format(
        lightning=symbols.LIGHTNING.value
    )

    usage = """
usage: vl [--debug DEBUG] [--config CONFIG]
          {up,down,start,distro_list,storage_dir,ansible_inventory} ..."""
    example = """
Example:

 We export the list of the distro in the virt-lightning.yaml file.
   $ vl distro_list > virt-lightning.yaml

 For each line of the virt-lightning.yaml, start a VM with the associated distro.
   $ vl up

 Once the VM are up, we can generate an Ansible inventory file:
   $ vl ansible_inventory

 The file is ready to be used by Ansible:
   $ ansible all -m ping -i inventory"""

    def list_from_yaml_file(value):
        file_path = pathlib.PosixPath(value)
        if not file_path.exists():
            raise argparse.ArgumentTypeError(
                "{path} does not exist.".format(path=value)
            )
        with file_path.open(encoding="UTF-8") as fd:
            content = yaml.safe_load(fd.read())
            if not isinstance(content, list):
                raise argparse.ArgumentTypeError(
                    "{path} should be a YAML list.".format(path=value)
                )
            return content

    vl_lightning_yaml_args = {
        "default": "virt-lightning.yaml",
        "help": "point on an alternative virt-lightning.yaml file (default: %(default)s)",
        "type": list_from_yaml_file,
        "dest": "virt_lightning_yaml",
    }

    context_args = {
        "default": "default",
        "help": "alternative context (default: %(default)s)",
        "dest": "context",
    }

    parent_parser = argparse.ArgumentParser(add_help=False)
    main_parser = argparse.ArgumentParser()
    main_parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Print extra information (default: %(default)s)",
    )
    main_parser.add_argument(
        "--config",
        help="path to configuration file",
        required=False,
        type=pathlib.PosixPath,
    )

    action_subparsers = main_parser.add_subparsers(title="action", dest="action")

    up_parser = action_subparsers.add_parser(
        "up", help="first", parents=[parent_parser]
    )
    up_parser.add_argument("--virt-lightning-yaml", **vl_lightning_yaml_args)
    up_parser.add_argument("--context", **context_args)

    down_parser = action_subparsers.add_parser(
        "down", help="first", parents=[parent_parser]
    )
    down_parser.add_argument("--context", **context_args)

    start_parser = action_subparsers.add_parser(
        "start", help="Start a new VM", parents=[parent_parser]
    )
    start_parser.add_argument(
        "--ssh",
        help="Automatically open a SSH connection.",
        action="store_true",
        default=False,
    )
    start_parser.add_argument("--memory", help="Memory in MB", type=int)
    start_parser.add_argument("--vcpus", help="Number of VCPUS", type=int)
    start_parser.add_argument("distro", help="Name of the distro", type=str)

    stop_parser = action_subparsers.add_parser(
        "stop", help="Stop a VM", parents=[parent_parser]
    )
    stop_parser.add_argument("name", help="Name of the VM", type=str)

    status_parser = action_subparsers.add_parser(
        "status", help="first", parents=[parent_parser]
    )
    status_parser.add_argument("--context", **context_args)

    action_subparsers.add_parser("distro_list", help="first", parents=[parent_parser])
    action_subparsers.add_parser(
        "storage_dir", help="Print the storage directory", parents=[parent_parser]
    )

    ansible_inventory_parser = action_subparsers.add_parser(
        "ansible_inventory",
        help="Print an ansible_inventory of the running environment",
        parents=[parent_parser],
    )
    ansible_inventory_parser.add_argument("--context", **context_args)

    ssh_parser = action_subparsers.add_parser(
        "ssh", help="SSH to a given host", parents=[parent_parser]
    )
    ssh_parser.add_argument("name", help="Name of the host", type=str, nargs="?")

    console_parser = action_subparsers.add_parser(
        "console", help="Open the console of a given host", parents=[parent_parser]
    )
    console_parser.add_argument("name", help="Name of the host", type=str, nargs="?")

    args = main_parser.parse_args()
    if not args.action:
        print(title)  # noqa: T001
        print(usage)  # noqa: T001
        print(example)  # noqa: T001
        exit(1)

    configuration = Configuration()
    if args.config:
        configuration.load_file(args.config)

    if args.debug:
        logger.setLevel(logging.DEBUG)

    globals()[args.action](configuration=configuration, **vars(args))
