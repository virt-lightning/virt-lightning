#!/usr/bin/env python3

import io
import logging
import time
import yaml
import pathlib
import virt_lightning.api as vla
from virt_lightning.configuration import Configuration

logger = logging.getLogger("virt_lightning")
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
logger.addHandler(ch)


number_of_runs = 1

index_md = pathlib.Path("www/images/index.md")

distros = yaml.safe_load(index_md.open("r"))
log_dir = pathlib.Path("/tmp/log")
local_dir = pathlib.Path("/var/lib/virt-lightning/pool/upstream/")

configuration = Configuration()
for distro in distros:
    qcow2_path = local_dir / (distro + ".qcow2")
    if not qcow2_path.exists():
        print("Fetching {distro}".format(distro=distro))
        try:
            vla.fetch(configuration=configuration, distro=distro)
        except vla.ImageNotFoundUpstream:
            print("Image not found")
            continue
    log_file = log_dir / (distro + ".log")
    sum = 0
    for i in range(number_of_runs):
        my_fd = log_file.open("w")
        vla.down(configuration)
        start_time = time.time()
        vla.start(configuration=configuration, distro=distro, enable_console=True, console_fd=my_fd) 
        elapsed_time = time.time() - start_time
        sum += elapsed_time
        print("- elapsed_time={elapsed_time:06.2f}".format(elapsed_time=elapsed_time))
    print("FINAL distro={distro}: {result}".format(distro=distro, result=sum/number_of_runs))
