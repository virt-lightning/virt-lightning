"""
⚡Virt-Lightning ⚡cli2 CLI
"""

import cli2
import inspect
import sys
from virt_lightning import api, shell, ui
from virt_lightning.configuration import Configuration


configuration = Configuration()


class Command(cli2.Command):
    def setargs(self):
        super().setargs()
        self['config'] = cli2.Argument(
            self,
            inspect.Parameter(
                'config',
                inspect.Parameter.KEYWORD_ONLY,
            ),
            doc='Configuration file to use',
        )

    def call(self, *args, **kwargs):
        cfgpath = kwargs.pop('config', None)
        if cfgpath:
            configuration.load_file(args.config)
        try:
            return super().call(*args, **kwargs)
        except api.ImageNotFoundLocallyError as e:
            print(f'Image not found from url: {e.name}')  # noqa: T001
            sys.exit(1)
        except api.CannotConnectToLibvirtError:
            shell.how_to_fix_auth_error()
        except api.VMNotRunningError as e:
            print(f'The following instance is not running: {e.name}')  # noqa: T001
            sys.exit(1)


cli = cli2.Group(doc=__doc__, cmdclass=Command, posix=True, log=False)


@cli.cmd(color='green')
def status():
    """
    Dump the status of Virt-Lightning VMs.
    """
    table = cli2.Table()
    for status in api.status(configuration=configuration):
        table.append([
            status['name'],
            '@'.join([status['username'], status['ipv4']]),
            status['distro'],
            status['context'] if status['context'] != 'default' else '',
        ])
    table.print()


@cli.cmd
def up(context='default', console=True, yaml='virt-lightning.yaml'):
    """
    Start VMs defined in virt-lightning.yaml

    :param context: The context name
    :param console: Show console output during VM creation
    :param yaml: Alternative path to virt-lightning.yaml
    """

    # pasted straight from virt_lightning.shell.main closure
    def list_from_yaml_file(value):
        import pathlib
        import yaml
        file_path = pathlib.PosixPath(value)
        if not file_path.exists():
            raise argparse.ArgumentTypeError(f"{value} does not exist.")
        with file_path.open(encoding="UTF-8") as fd:
            content = yaml.safe_load(fd.read())
            if not isinstance(content, list):
                raise argparse.ArgumentTypeError(f"{value} should be a YAML list.")
            return content

    api.up(
        configuration=configuration,
        enable_console=console,
        context=context,
        virt_lightning_yaml=list_from_yaml_file(yaml),
    )


@cli.cmd(color='red')
def down(context='default'):
    """
    Destroy VMs.
    """
    api.down(configuration=configuration, context=context)


@cli.cmd
def create(distro, name=None, vcpus=None, memory=None, context='default',
           console=True):
    """
    Create and start a new VM.

    :param name: Name of the VM
    :param vcpus: Number of vCpus
    :param memory: RAM in MB
    :param console: Show console output
    """
    api.start(
        configuration=configuration,
        context=context,
        name=name,
        vcpus=vcpus,
        memory=memory,
        distro=distro,
        enable_console=console,
    )


@cli.cmd(color='green')
def distro_list():
    """
    List distributions supported by Virt-Lightning.
    """
    for distro_name in api.distro_list(configuration=configuration):
        print("- distro: {0}".format(distro_name))  # noqa: T001


@cli.cmd(color='green')
def storage_dir():
    """
    Dump storage directory path for Virt-Lightning VMs.
    """
    print(api.storage_dir(configuration=configuration))


@cli.cmd(color='green')
def ansible_inventory():
    """
    Dump ansible inventory file.

    Example:

        vl2 ansible_inventory > inventory.ini
        ansible -m ping -i inventory.ini all
    """
    print(api.ansible_inventory(configuration=configuration))


@cli.cmd(color='green')
def ssh_config(context='default'):
    """
    Dump ssh configuration for the VMs.
    """
    print(api.ssh_config(configuration=configuration, context=context))


@cli.cmd(color='green')
def ssh(name=None, context='default'):
    """
    Open an SSH connection on a VM.

    :param name: VM name, if not specified then VM selector UI will ask.
    """
    if name:
        api.exec_ssh(configuration=configuration, name=name)

    def go_ssh(domain):
        domain.exec_ssh()

    ui.Selector(
        api.list_domains(configuration=configuration),
        go_ssh,
    )


@cli.cmd(color='green')
def fetch(distro):
    """
    Fetch a distribution image.

    :param distro: Name of the distribution for the VM image to download.
    """
    def progress_callback(cur, length):
        percent = (cur * 100) / length
        line = "🌍 ➡️  💻 [{percent:06.2f}%]  {done:6}MB/{full}MB\r".format(
            percent=percent,
            done=int(cur / api.MB),
            full=int(length / api.MB),
        )
        print(line, end="")  # noqa: T001

    try:
        api.fetch(
            configuration=configuration,
            progress_callback=progress_callback,
            distro=distro,
        )
    except api.ImageNotFoundUpstreamError:
        print(  # noqa: T001
            f"Distro {distro} cannot be downloaded.\n"
            f"  Visit {api.BASE_URL}/images/ or private image hub"
            "to get an up to date list."
        )
        exit(1)


@cli.cmd(color='green')
def console(name):
    """
    Open a serial console to a named VM.

    :param name: VM name
    """
    shell.console(configuration=configuration, name=name)


@cli.cmd(color='green')
def viewer(name):
    """
    Open a graphical screen to a named VM.

    :param name: VM name
    """
    shell.viewer(configuration=configuration, name=name)
