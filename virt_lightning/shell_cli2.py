"""
⚡Virt-Lightning ⚡cli2 CLI
"""

import cli2
import inspect
import sys
from virt_lightning import api
from virt_lightning.shell import how_to_fix_auth_error
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
            how_to_fix_auth_error()
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
