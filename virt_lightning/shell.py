#!/usr/bin/env python3

import argparse
import pathlib
import re
import sys
import time

import virt_lightning.virt_lightning as vl
from virt_lightning.configuration import Configuration
from virt_lightning.symbols import get_symbols

import yaml


CURSOR_UP_ONE = "\x1b[1A"
ERASE_LINE = "\x1b[2K"


def up(virt_lightning_yaml, configuration, context, **kwargs):
    hv = vl.LibvirtHypervisor(configuration.libvirt_uri)
    hv.init_network(configuration.bridge)
    hv.init_storage_pool(configuration.storage_pool)

    status_line = "Starting:"

    for host in virt_lightning_yaml:
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
        status_line += "🗲{name} ".format(**host)
        print(status_line)
        domain = hv.create_domain(name=host["name"], distro=host["distro"])
        domain.context = context
        domain.load_ssh_key_file(configuration.ssh_key_file)
        domain.username = configuration.username

        if configuration.root_password:
            domain.root_password(configuration.root_password)
        else:
            domain.root_password(host.get("root_password"))

        domain.vcpus(host.get("vcpus"))
        domain.memory(host.get("memory", 768))
        root_disk_path = hv.create_disk(name=host["name"], backing_on=host["distro"])
        domain.add_root_disk(root_disk_path)
        domain.attachBridge(configuration.bridge)
        domain.set_ip(ipv4=hv.get_free_ipv4(), gateway=hv.gateway, dns=hv.dns)
        domain.add_swap_disk(hv.create_disk(host["name"] + "-swap", size=1))
        hv.start(domain)
        sys.stdout.write(CURSOR_UP_ONE)
        sys.stdout.write(ERASE_LINE)

    time.sleep(2)
    status_line_template = (
        "{icon}IPv4 ready: {with_ipv4}/{all_vms}    "
        "{icon}SSH ready: {with_ssh}/{all_vms}"
    )
    print(status_line)
    icons = ["☆", "★"]
    while True:
        icons.reverse()
        status = get_status(hv, context=context)
        all_vms = len(status)
        with_ipv4 = len([i for i in status if i["ipv4"]])
        with_ssh = len([i for i in status if i["ssh_ping"]])
        status_line = status_line_template.format(
            icon=icons[0], all_vms=all_vms, with_ipv4=with_ipv4, with_ssh=with_ssh
        )
        sys.stdout.write(CURSOR_UP_ONE)
        sys.stdout.write(ERASE_LINE)
        print(status_line)
        time.sleep(0.5)
        if all_vms == with_ssh:
            print("Done! You can now follow the deployment:")
            print("You can also access the serial console of the VM:\n\n")
            for host in status:
                print(
                    (
                        "⚈ {name}:\n    console⇝ virsh console {name}\n"
                        "    ssh⇝ ssh {username}@{ipv4}"
                    ).format(**host)
                )
            break


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
                    name=domain.name, ipv4=domain.get_ipv4(), username=domain.username
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
                "ipv4": domain.get_ipv4(),
                "context": domain.context,
                "username": domain.username,
                "ssh_ping": domain.ssh_ping(),
            }
        )
    return status


def status(configuration, context=None, **kwargs):
    hv = vl.LibvirtHypervisor(configuration.libvirt_uri)
    results = {}

    symbols = get_symbols()

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
            "ssh_ping": iconify(status["ssh_ping"]),
        }

    for _ in range(0, len(results) + 1):
        sys.stdout.write(CURSOR_UP_ONE)
        sys.stdout.write(ERASE_LINE)

    print("[host]        [username@IP]")
    for _, v in sorted(results.items()):
        print("{name:<13} {username}@{ipv4:>5} {ssh_ping}".format(**v))


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


def storage_dir(configuration):
    hv = vl.LibvirtHypervisor(configuration.libvirt_uri)
    hv.init_storage_pool(configuration.storage_pool)
    print(hv.get_storage_dir())


def main():

    usage = """⚡ Virt-Lightning ⚡

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

    def list_from_yaml_file(path):
        with pathlib.PosixPath(path).open(encoding="UTF-8") as fd:
            content = yaml.load(fd.read())
            if not isinstance(content, list):
                raise argparse.ArgumentTypeError(
                    "{path} should be a YAML list.".format(path=path)
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
        type=argparse.FileType("r", encoding="UTF-8"),
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

    args = main_parser.parse_args()
    if not args.action:
        print(usage)
        print(example)
        exit(1)

    configuration = Configuration()
    if args.config:
        configuration.load_fd(args.config)

    globals()[args.action](configuration=configuration, **vars(args))
