#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Red Hat, Inc
# Copyright (C) 2020 Gonéri Le Bouder
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import os

import setuptools


def _get_requirements():
    requirements_path = "{path}/{filename}".format(
        path=os.path.dirname(os.path.abspath(__file__)), filename="requirements.txt"
    )
    with open(requirements_path, "r", encoding="utf-8") as f:
        return f.read()


def _get_readme():
    readme_path = "{path}/{filename}".format(
        path=os.path.dirname(os.path.abspath(__file__)), filename="README.md"
    )

    with open(readme_path, "r", encoding="utf-8") as f:
        return f.read()


setuptools.setup(
    name="virt-lightning",
    version="2.0.0",
    packages=setuptools.find_packages(),
    author="Gonéri Le Bouder",
    author_email="goneri@lebouder.net",
    description="Deploy your testing VM in a couple of seconds",
    long_description=_get_readme(),
    long_description_content_type="text/markdown",
    install_requires=_get_requirements(),
    url="https://virt-lightning.org",
    use_scm_version={"write_to": "virt_lightning/version.py"},
    license="Apache v2.0",
    platforms=["linux"],
    classifiers=[
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Topic :: System :: Distributed Computing",
    ],
    entry_points={
        "console_scripts": [
            "virt-lightning = virt_lightning.shell:main",
            "vl = virt_lightning.shell:main",
        ]
    },
    setup_requires=["setuptools_scm"],
)
