#!/usr/bin/env python3

import argparse
import logging
import pathlib
import libvirt
import os
import yaml
import sys


import virt_lightning.api
from virt_lightning.configuration import Configuration
from virt_lightning.symbols import get_symbols
import virt_lightning.virt_lightning as vl
import virt_lightning.ui as ui


symbols = get_symbols()
logger = logging.getLogger("virt_lightning")
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
logger.addHandler(ch)


def get_local_libvirt_group():
    etc_group_content = pathlib.Path("/etc/group").read_text()
    for entry in etc_group_content.split("\n"):
        group, _, gid = entry.split(":")[0:3]
        if group == "libvirt":
            return (group, gid)


def how_to_fix_auth_error():
    import getpass

    libvirt_group = get_local_libvirt_group()
    if not libvirt_group:
        return
    group, gid = libvirt_group
    if gid not in os.getgroups():
        print("Virt-Lightning cannot access the local libvirt service.")  # noqa: T001
        print(  # noqa: T001
            (
                f"Your user should probably be in the {group} group. "
                f"You can add the user {getpass. getuser()} in the group {group} with the "
                "following command:"
            )
        )
        print(  # noqa: T001
            f"    sudo usermod --append --groups libvirt {getpass.getuser()}"
        )


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


def viewer(configuration, name=None, **kwargs):
    conn = libvirt.open(configuration.libvirt_uri)
    hv = vl.LibvirtHypervisor(conn)

    def virt_viewer_binary():
        paths = [
            pathlib.PosixPath(i, "virt-viewer")
            for i in os.environ["PATH"].split(os.pathsep)
        ]
        for exe in paths:
            if exe.exists():
                return exe
        raise Exception("Failed to find virt-viewer in: ", paths)

    def go_viewer(domain):
        pid = os.fork()
        if pid == 0:
            os.close(1)
            os.close(2)
            os.execlp(
                virt_viewer_binary(),
                "virt-viewer",
                "-c",
                configuration.libvirt_uri,
                "--domain-name",
                domain.name,
            )
        else:
            sys.exit(0)

    if name:
        go_viewer(hv.get_domain_by_name(name))

    ui.Selector(sorted(hv.list_domains()), go_viewer)


def progress_callback(cur, length):
    percent = (cur * 100) / length
    line = "🌍 ➡️  💻 [{percent:06.2f}%]  {done:6}MB/{full}MB\r".format(
        percent=percent,
        done=int(cur / virt_lightning.api.MB),
        full=int(length / virt_lightning.api.MB),
    )
    print(line, end="")  # noqa: T001


def list_from_yaml_file(value):
    file_path = pathlib.PosixPath(value)
    if not file_path.exists():
        raise argparse.ArgumentTypeError(f"{value} does not exist.")
    with file_path.open(encoding="UTF-8") as fd:
        content = yaml.safe_load(fd.read())
        if not isinstance(content, list):
            raise argparse.ArgumentTypeError(f"{value} should be a YAML list.")
        return content


def main():

    title = "{lightning} Virt-Lightning {lightning}".format(
        lightning=symbols.LIGHTNING.value
    )

    usage = """
usage: vl [--debug DEBUG] [--config CONFIG] COMMAND

Run vl without a command to see list of accepted commands.
"""
    example = """
Example:

 We export the list of the distro in the virt-lightning.yaml file.
   $ vl distro_list > virt-lightning.yaml

 For each line of the virt-lightning.yaml, start a VM with the associated distro.
   $ vl up

 Once the VM are up, we can generate an Ansible inventory file:
   $ vl ansible_inventory

 The file is ready to be used by Ansible:
   $ ansible all -m ping -i inventory

Commands:
    up                  Start VMs defined in virt-lightning.yaml
    down                Delete all VMs created by virt-lightning
    start               Start a new VM
    stop                Delete a VM
    distro_list         Dump list of supported distros
    storage_dir         Dump the VM image storage directory
    ansible_inventory   Dump an inventory file for ansible
    ssh_config          Dump an SSH config
    console             Open console on a VM
    viewer              Open VM with virt-viewer
    """

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
        "up",
        help="Start the VM listed in the virt-lightning.yaml file",
        parents=[parent_parser],
    )
    up_parser.add_argument("--virt-lightning-yaml", **vl_lightning_yaml_args)
    up_parser.add_argument("--context", **context_args)

    down_parser = action_subparsers.add_parser(
        "down",
        help="Destroy all the VM created with VirtLightning",
        parents=[parent_parser],
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
    start_parser.add_argument("--name", help="Name of the VM", type=str)
    start_parser.add_argument("--memory", help="Memory in MB", type=int)
    start_parser.add_argument("--vcpus", help="Number of VCPUS", type=int)
    start_parser.add_argument("--context", **context_args)
    start_parser.add_argument(
        "--show-console",
        help="Suppress console output during VM creation",
        type=bool,
        dest="enable_console",
        default=True,
    )
    start_parser.add_argument("distro", help="Name of the distro", type=str)

    stop_parser = action_subparsers.add_parser(
        "stop", help="Stop and delete a VM", parents=[parent_parser]
    )
    stop_parser.add_argument("name", help="Name of the VM", type=str)

    status_parser = action_subparsers.add_parser(
        "status", help="List the VM currently running", parents=[parent_parser]
    )
    status_parser.add_argument("--context", **context_args)

    action_subparsers.add_parser(
        "distro_list",
        help="List all the images available locally",
        parents=[parent_parser],
    )
    action_subparsers.add_parser(
        "storage_dir", help="Print the storage directory", parents=[parent_parser]
    )

    ansible_inventory_parser = action_subparsers.add_parser(
        "ansible_inventory",
        help="Print an ansible_inventory of the running environment",
        parents=[parent_parser],
    )
    ansible_inventory_parser.add_argument("--context", **context_args)

    ssh_config_parser = action_subparsers.add_parser(
        "ssh_config",
        help="Print a ssh config of the running environment",
        parents=[parent_parser],
    )
    ssh_config_parser.add_argument("--context", **context_args)

    ssh_parser = action_subparsers.add_parser(
        "ssh", help="SSH to a given host", parents=[parent_parser]
    )
    ssh_parser.add_argument("name", help="Name of the host", type=str, nargs="?")

    console_parser = action_subparsers.add_parser(
        "console", help="Open the console of a given host", parents=[parent_parser]
    )
    console_parser.add_argument("name", help="Name of the host", type=str, nargs="?")

    viewer_parser = action_subparsers.add_parser(
        "viewer",
        help="Open the SPICE console of a given host with virt-viewer",
        parents=[parent_parser],
    )
    viewer_parser.add_argument("name", help="Name of the host", type=str, nargs="?")

    fetch_parser = action_subparsers.add_parser(
        "fetch", help="Fetch a VM image", parents=[parent_parser]
    )
    fetch_parser.add_argument("distro", help="Name of the VM image", type=str)

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

    if args.action == "ansible_inventory":
        print(  # noqa: T001
            virt_lightning.api.ansible_inventory(
                configuration=configuration, **vars(args)
            )
        )
    elif args.action == "ssh_config":
        print(  # noqa: T001
            virt_lightning.api.ssh_config(configuration=configuration, **vars(args))
        )
    elif args.action == "distro_list":
        for distro_name in virt_lightning.api.distro_list(
            configuration=configuration, **vars(args)
        ):
            print("- distro: {0}".format(distro_name))  # noqa: T001
    elif args.action == "storage_dir":
        print(  # noqa: T001
            virt_lightning.api.storage_dir(configuration=configuration, **vars(args))
        )
    elif args.action == "status":
        results = {}
        for status in virt_lightning.api.status(
            configuration=configuration, **vars(args)
        ):
            results[status["name"]] = {
                "name": status["name"],
                "ipv4": status["ipv4"] or "waiting",
                "context": status["context"],
                "username": status["username"],
                "distro": status["distro"],
            }

        output_template = (
            "{computer} {name:<13}   {arrow}   {username}@{ipv4:>5} [{distro}]"
        )
        for _, v in sorted(results.items()):
            print(  # noqa: T001
                output_template.format(
                    computer=symbols.COMPUTER.value,
                    arrow=symbols.RIGHT_ARROW.value,
                    **v,
                )
            )
    elif args.action == "console":
        console(configuration=configuration, name=args.name)
    elif args.action == "viewer":
        viewer(configuration=configuration, name=args.name)
    elif args.action == "ssh":
        if args.name:
            virt_lightning.api.exec_ssh(configuration=configuration, name=args.name)

        def go_ssh(domain):
            domain.exec_ssh()

        ui.Selector(
            virt_lightning.api.list_domains(configuration=configuration, **vars(args)),
            go_ssh,
        )
    elif args.action == "fetch":
        try:
            virt_lightning.api.fetch(
                configuration=configuration,
                progress_callback=progress_callback,
                **vars(args),
            )
        except virt_lightning.api.CannotConnectToLibvirtError:
            how_to_fix_auth_error()
        except virt_lightning.api.ImageNotFoundUpstreamError:
            print(  # noqa: T001
                f"Distro {args.distro} cannot be downloaded.\n"
                f"  Visit {virt_lightning.api.BASE_URL}/images/ or private image hub"
                "to get an up to date list."
            )
            exit(1)
    elif args.action in ["up", "start"]:
        action_func = getattr(virt_lightning.api, args.action)
        try:
            action_func(configuration=configuration, **vars(args))
        except virt_lightning.api.ImageNotFoundLocallyError as e:
            print(f"Image not found from url: {e.name}")  # noqa: T001
            exit(1)
        except virt_lightning.api.CannotConnectToLibvirtError:
            how_to_fix_auth_error()
        except virt_lightning.api.VMNotRunningError as e:
            print(f"The following instance is not running: {e.name}")  # noqa: T001
            exit(1)
    else:
        try:
            action_func = getattr(virt_lightning.api, args.action)
            action_func(configuration=configuration, **vars(args))
        except virt_lightning.api.VMNotFoundError as e:
            logger.error("VM {name} not found".format(name=e.name))
        except virt_lightning.api.ImageNotFoundLocallyError as e:
            logger.error(
                (
                    "ℹ️ You may be able to download the image with the "
                    "`vl fetch {name}` command."
                ).format(name=e.name)
            )
            exit(1)
