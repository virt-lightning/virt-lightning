#!/usr/bin/env python3

from jinja2 import Template
from pathlib import PosixPath
from pathlib import Path
import yaml

vars_path = PosixPath("ansible/roles/virt_lightning/vars/").glob("*")

template = Template(Path("README.md.j2").read_text())


distros = []
for distro in vars_path:
    content = yaml.load(distro.read_text())
    content["name"] = distro.stem
    distros.append(content)

Path("README.md").write_text(template.render(distros=distros))
