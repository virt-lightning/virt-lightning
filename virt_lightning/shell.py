#!/usr/bin/env python3

import argparse
import getpass
import glob
import os
import pathlib
import re
import sys
import time

import virt_lightning as vl
from virt_lightning.symbols import get_symbols
from virt_lightning.configuration import ReadConfigShell, DEFAULT_CONFIGFILE

import yaml


CURSOR_UP_ONE = "\x1b[1A"
ERASE_LINE = "\x1b[2K"


def load_vm_config(config_file):
    if not os.path.isfile(config_file):
        print("Configuration file not found")
        return None

    try:
        with open(config_file, "r") as fd:
            host_definitions = yaml.load(fd)

            return host_definitions

    except IOError:
        print("Error while open configuration file")
    except yaml.YAMLError as e:
        print("Can not parse yaml file", e)

    return None


def up(configuration, virt_lightning_yaml_path, context):
    host_definitions = load_vm_config(virt_lightning_yaml_path)

    if not host_definitions:
        return

    hv = vl.LibvirtHypervisor(configuration)

    status_line = "Starting:"

    for host in host_definitions:
        if "name" not in host:
            host["name"] = re.sub(r"\W+", "", host["distro"])

        if hv.get_domain_by_name(host["name"]):
            print("Domain {name} already exists!".format(**host))
            exit(1)

        # Unfortunatly, i can't decode that symbol
        # that symbol more well add to check encoding block
        status_line += "🗲{name} ".format(**host)
        print(status_line)
        domain = hv.create_domain(**host)
        domain.context(context)
        domain.ssh_key_file(configuration.ssh_key_file)
        domain.username(configuration.username)

        if configuration.root_password:
            domain.root_password(configuration.root_password)
        else:
            domain.root_password(host.get("root_password"))

        domain.vcpus(host.get("vcpus"))
        domain.memory(host.get("memory", 768))
        root_disk_path = hv.create_disk(name=host["name"], backing_on=host["distro"])
        domain.add_root_disk(root_disk_path)
        domain.attachBridge(configuration.bridge)
        domain.set_ip(
            ipv4=hv.get_free_ipv4(), gateway="192.168.122.1", dns="192.168.122.1"
        )
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


def ansible_inventory(configuration, context):
    hv = vl.LibvirtHypervisor(configuration)

    for domain in hv.list_domains():
        if domain.context() == context:
            print(
                "{name} ansible_host={ipv4} ansible_username={username}".format(
                    name=domain.name(),
                    ipv4=domain.get_ipv4(),
                    username=domain.username(),
                )
            )


def get_status(hv, context):
    status = []
    for domain in hv.list_domains():
        if context and context != domain.context():
            continue
        name = domain.name()
        status.append(
            {
                "name": name,
                "ipv4": domain.get_ipv4(),
                "context": domain.context(),
                "username": domain.username(),
                "ssh_ping": domain.ssh_ping(),
            }
        )
    return status


def status(configuration, context=None, live=False):
    hv = vl.LibvirtHypervisor(configuration)
    results = {}

    symbols = get_symbols()

    def iconify(v):
        if isinstance(v, str):
            return v
        elif v:
            return symbols.CHECKMARK.value
        else:
            return symbols.CROSS.value

    while True:
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
        if not live:
            break
        time.sleep(0.5)


def down(configuration, context):
    hv = vl.LibvirtHypervisor(configuration)
    for domain in hv.list_domains():
        if context and domain.context() != context:
            continue
        domain.clean_up()


def list_distro(configuration):
    hv = vl.LibvirtHypervisor(configuration)
    path = hv.get_storage_dir()
    for path in glob.glob(path + "/upstream/*.qcow2"):
        distro = pathlib.Path(path).stem
        if "no-cloud-init" not in distro:
            print("- distro: {distro}".format(distro=distro))


def storage_dir(configuration):
    hv = vl.LibvirtHypervisor(configuration)
    print(hv.get_storage_dir())


def main():

    example = """
    Example:

      # We export the list of the distro in the virt-lightning.yaml file.
      $ vl distro > virt-lightning.yaml

      # For each line, virt-lightning will start a VM with the associated distro.
      $ vl up

      # Once the VM are up, we can generate an Ansible inventory file:
      $ vl ansible_inventory

      # The file is ready to be used by Ansible:
      $ ansible all -m ping -i inventory


    """

    parser = argparse.ArgumentParser(
        description="virt-lightning",
        epilog=example,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "action",
        choices=[
            "up",
            "down",
            "status",
            "ansible_inventory",
            "distro",
            "clean_all",
            "status_all",
            "status_live",
            "storage_dir",
        ],
        help="The action to call.",
    )
    parser.add_argument(
        "--virt-lightning-yaml",
        default="virt-lightning.yaml",
        help="point on an alternative virt-lightning.yaml file (default: %(default)s)",
    )
    parser.add_argument(
        "--context",
        default="default",
        help="change the name of the context (default: %(default)s)",
    )
    parser.add_argument(
        "--config",
        help="path to configuration file",
        required=False,
        default=DEFAULT_CONFIGFILE,
    )

    args = parser.parse_args()

    try:
        configuration = ReadConfigShell(args.config).load()
    except FileNotFoundError:
        print("Configuration file not found")
        exit(1)
    except:
        print("Can not get configuration from file")
        exit(1)

    if args.action == "up":
        up(configuration, args.virt_lightning_yaml, args.context)
    elif args.action == "down":
        down(configuration, args.context)
    elif args.action == "ansible_inventory":
        ansible_inventory(configuration, args.context)
    elif args.action == "distro":
        list_distro(configuration)
    elif args.action == "clean_all":
        down(configuration)
    elif args.action == "status_all":
        status(configuration)
    elif args.action == "status":
        status(configuration, args.context)
    elif args.action == "status_live":
        status(configuration, args.context, True)
    elif args.action == "storage_dir":
        storage_dir(configuration)
