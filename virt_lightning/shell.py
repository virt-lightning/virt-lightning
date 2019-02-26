#!/usr/bin/env python3

from concurrent.futures import ThreadPoolExecutor
import argparse
import asyncio
import os
import pathlib
import re
import sys

import libvirt
import libvirtaio
import yaml

from virt_lightning.configuration import Configuration
from virt_lightning.symbols import get_symbols
import virt_lightning.ui as ui
import virt_lightning.virt_lightning as vl

symbols = get_symbols()

def up(virt_lightning_yaml, configuration, context, **kwargs):
    hv = vl.LibvirtHypervisor(configuration.libvirt_uri)
    hv.init_network(configuration.network_name, configuration.network_cidr)
    hv.init_storage_pool(configuration.storage_pool)

    def start_domain(host):
        if host["distro"] not in hv.distro_available():
            print("distro not available:", host["distro"])
            print("Please select on of the following distro:", hv.distro_available())
            exit()

        if "name" not in host:
            host["name"] = re.sub(r"\W+", "", host["distro"])

        if hv.get_domain_by_name(host["name"]):
            print("Domain {name} already exists!".format(**host))
            exit(1)

        # Unfortunatly, i can't decode that symbol
        # that symbol more well add to check encoding block
        sys.stdout.write("{lightning}{name} ".format(lightning=symbols.LIGHTNING.value, **host))
        domain = hv.create_domain(name=host["name"], distro=host["distro"])
        domain.context = context
        domain.load_ssh_key_file(configuration.ssh_key_file)
        domain.username = configuration.username
        domain.root_password = host.get("root_password", configuration.root_password)

        domain.vcpus(host.get("vcpus"))
        domain.memory(host.get("memory", 768))
        root_disk_path = hv.create_disk(name=host["name"], backing_on=host["distro"])
        domain.add_root_disk(root_disk_path)
        domain.attachNetwork(configuration.network_name)
        domain.ipv4 = hv.get_free_ipv4()
        domain.add_swap_disk(hv.create_disk(host["name"] + "-swap", size=1))
        hv.start(domain)
        return domain

    def myDomainEventAgentLifecycleCallback(conn, dom, state, reason, opaque):
        if state == 1:
            dom.setUserPassword("root", "root")
            print("{name} agent is online".format(name=dom.name()))

    async def deploy():
        futures = []
        for host in virt_lightning_yaml:
            futures.append(loop.run_in_executor(pool, start_domain, host))

        domain_reachable_futures = []
        for f in futures:
            await f
            domain_reachable_futures.append(f.result().reachable())
        print("... ok Waiting...")

        for f in domain_reachable_futures:
            await f

    pool = ThreadPoolExecutor(max_workers=10)
    loop = asyncio.get_event_loop()
    libvirtaio.virEventRegisterAsyncIOImpl(loop=loop)
    vc = libvirt.open("qemu:///system")
    vc.setKeepAlive(5, 3)
    vc.domainEventRegisterAny(
        None,
        libvirt.VIR_DOMAIN_EVENT_ID_AGENT_LIFECYCLE,
        myDomainEventAgentLifecycleCallback,
        None,
    )
    loop.run_until_complete(deploy())


def ansible_inventory(configuration, context, **kwargs):
    hv = vl.LibvirtHypervisor(configuration.libvirt_uri)

    ssh_cmd_template = (
        "{name} ansible_host={ipv4} ansible_username={username} "
        'ansible_ssh_common_args="-o UserKnownHostsFile=/dev/null '
        '-o StrictHostKeyChecking=no"'
    )

    for domain in hv.list_domains():
        if domain.context == context:
            print(
                ssh_cmd_template.format(
                    name=domain.name, ipv4=domain.ipv4.ip, username=domain.username
                )
            )


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
    hv = vl.LibvirtHypervisor(configuration.libvirt_uri)
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

    for _, v in sorted(results.items()):
        print("  {name:<13}   ⇛   {username}@{ipv4:>5}".format(**v))


def ssh(configuration, name=None, **kwargs):
    hv = vl.LibvirtHypervisor(configuration.libvirt_uri)

    def go_ssh(domain):
        os.execlp(
            "ssh",
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "{username}@{ipv4}".format(username=domain.username, ipv4=domain.ipv4.ip),
        )

    if name:
        go_ssh(hv.get_domain_by_name(name))

    ui.Selector(sorted(hv.list_domains()), go_ssh)


def console(configuration, name=None, **kwargs):
    hv = vl.LibvirtHypervisor(configuration.libvirt_uri)

    def go_console(domain):
        os.execlp(
            "virsh", "virsh", "-c", configuration.libvirt_uri, "console", domain.name
        )

    if name:
        go_console(hv.get_domain_by_name(name))

    ui.Selector(sorted(hv.list_domains()), go_console)


def down(configuration, context, **kwargs):
    hv = vl.LibvirtHypervisor(configuration.libvirt_uri)
    hv.init_storage_pool(configuration.storage_pool)
    for domain in hv.list_domains():
        if context and domain.context != context:
            continue
        hv.clean_up(domain)


def distro_list(configuration, **kwargs):
    hv = vl.LibvirtHypervisor(configuration.libvirt_uri)
    hv.init_storage_pool(configuration.storage_pool)
    for distro in hv.distro_available():
        print("- distro: {distro}".format(distro=distro))


def storage_dir(configuration, **kwargs):
    hv = vl.LibvirtHypervisor(configuration.libvirt_uri)
    hv.init_storage_pool(configuration.storage_pool)
    print(hv.get_storage_dir())


def main():

    title = "{lightning} Virt-Lightning {lightning}".format(
        lightning=symbols.LIGHTNING.value)

    usage = """
usage: vl [--debug DEBUG] [--config CONFIG]
          {up,down,status,distro_list,storage_dir,ansible_inventory} ..."""
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
        with pathlib.PosixPath(value).open(encoding="UTF-8") as fd:
            content = yaml.load(fd.read())
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
        "--debug", default=False, help="Print extra information (default: %(default)s)"
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

    ssh_parser = action_subparsers.add_parser(
        "console", help="Open the console of a given host", parents=[parent_parser]
    )
    ssh_parser.add_argument("name", help="Name of the host", type=str, nargs="?")

    args = main_parser.parse_args()
    if not args.action:
        print(title)
        print(usage)
        print(example)
        exit(1)

    configuration = Configuration()
    if args.config:
        configuration.load_file(args.config)

    globals()[args.action](configuration=configuration, **vars(args))
