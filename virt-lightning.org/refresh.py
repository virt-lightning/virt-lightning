#!/usr/bin/env python3

import json
import re
from pathlib import Path
from textwrap import dedent

import urllib3

configuration = {
    "debian-9": "https://cdimage.debian.org/cdimage/openstack/current-9/debian-9-openstack-amd64.qcow2",
    "debian-10": "https://cdimage.debian.org/cdimage/openstack/current-10/debian-10-openstack-amd64.qcow2",
    "debian-11": "https://cdimage.debian.org/cdimage/cloud/bullseye/latest/debian-11-generic-amd64.qcow2",
    "debian-12": "https://cdimage.debian.org/cdimage/cloud/bookworm/latest/debian-12-generic-amd64.qcow2",
    "debian-13": "https://cloud.debian.org/images/cloud/trixie/daily/latest/debian-13-generic-amd64-daily.qcow2",
    "debian-sid": "https://cdimage.debian.org/cdimage/cloud/sid/daily/latest/debian-sid-generic-amd64-daily.qcow2",
    "centos-7": "http://cloud.centos.org/centos/7/images/CentOS-7-x86_64-GenericCloud.qcow2",
    "centos-6": "https://cloud.centos.org/centos/6/images/CentOS-6-x86_64-GenericCloud.qcow2",
    "centos-8": "https://cloud.centos.org/centos/8/x86_64/images/CentOS-8-GenericCloud-8.1.1911-20200113.3.x86_64.qcow2",
    "centos-8-stream": "https://cloud.centos.org/centos/8-stream/x86_64/images/CentOS-Stream-GenericCloud-8-latest.x86_64.qcow2",
    "centos-9-stream": "https://cloud.centos.org/centos/9-stream/x86_64/images/CentOS-Stream-GenericCloud-9-latest.x86_64.qcow2",
    "centos-stream-8": "https://cloud.centos.org/centos/8-stream/x86_64/images/CentOS-Stream-GenericCloud-8-latest.x86_64.qcow2",
    "centos-stream-9": "https://cloud.centos.org/centos/9-stream/x86_64/images/CentOS-Stream-GenericCloud-9-latest.x86_64.qcow2",
    "almalinux-8": "https://repo.almalinux.org/almalinux/8/cloud/x86_64/images/AlmaLinux-8-GenericCloud-latest.x86_64.qcow2",
    "almalinux-9": "https://repo.almalinux.org/almalinux/9/cloud/x86_64/images/AlmaLinux-9-GenericCloud-latest.x86_64.qcow2",
    "rockylinux-8": "https://download.rockylinux.org/pub/rocky/8/images/x86_64/Rocky-8-GenericCloud.latest.x86_64.qcow2",
    "rockylinux-9": "https://download.rockylinux.org/pub/rocky/9/images/x86_64/Rocky-9-GenericCloud.latest.x86_64.qcow2",
    "ubuntu-14.04": "https://cloud-images.ubuntu.com/trusty/current/trusty-server-cloudimg-amd64-disk1.img",
    "ubuntu-16.04": "https://cloud-images.ubuntu.com/xenial/current/xenial-server-cloudimg-amd64-disk1.img",
    "ubuntu-18.04": "https://cloud-images.ubuntu.com/bionic/current/bionic-server-cloudimg-amd64.img",
    "ubuntu-19.04": "https://cloud-images.ubuntu.com/disco/current/disco-server-cloudimg-amd64.img",
    "ubuntu-19.10": "https://cloud-images.ubuntu.com/eoan/current/eoan-server-cloudimg-amd64.img",
    "ubuntu-20.04": "https://cloud-images.ubuntu.com/focal/current/focal-server-cloudimg-amd64.img",
    "ubuntu-21.04": "https://cloud-images.ubuntu.com/hirsute/current/hirsute-server-cloudimg-amd64.img",
    "ubuntu-22.04": "https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img",
    "ubuntu-22.10": "https://cloud-images.ubuntu.com/kinetic/current/kinetic-server-cloudimg-amd64.img",
    "ubuntu-23.04": "https://cloud-images.ubuntu.com/lunar/current/lunar-server-cloudimg-amd64.img",
    "ubuntu-23.10": "https://cloud-images.ubuntu.com/mantic/current/mantic-server-cloudimg-amd64.img",
    "ubuntu-24.04": "https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img",
    "ubuntu-24.10": "https://cloud-images.ubuntu.com/oracular/current/oracular-server-cloudimg-amd64.img",
    "cirros-0.4.0": "http://download.cirros-cloud.net/0.4.0/cirros-0.4.0-x86_64-disk.img",
    "opensuse-leap-15.2": "https://download.opensuse.org/repositories/Cloud:/Images:/Leap_15.2/images/openSUSE-Leap-15.2-OpenStack.x86_64.qcow2",
    "gentoo-latest": "http://gentoo.osuosl.org/experimental/amd64/openstack/gentoo-openstack-amd64-default-latest.qcow2",
    "gentoo-systemd-latest": "http://gentoo.osuosl.org/experimental/amd64/openstack/gentoo-openstack-amd64-systemd-latest.qcow2",
    "amazon2-20210126.0": "https://cdn.amazonlinux.com/os-images/2.0.20210126.0/kvm/amzn2-kvm-2.0.20210126.0-x86_64.xfs.gpt.qcow2",
    "amazon2-20230320.0": "https://cdn.amazonlinux.com/os-images/2.0.20230320.0/kvm/amzn2-kvm-2.0.20230320.0-x86_64.xfs.gpt.qcow2",
}


class Image:
    def retrieve_metadata(self):
        yaml_url = re.sub(r".qcow2", ".yaml", self.qcow2_url)
        resp = urllib3.request("GET", yaml_url)
        if resp.status == 200:
            self.yaml_url = yaml_url
            for line in resp.data.decode().split("\n"):
                if ": " in line:
                    k, v = line.split(": ")
                    self.meta[k] = v.strip()

    def __init__(self, name, qcow2_url):
        self.name = name
        self.qcow2_url = qcow2_url
        self.meta: dict[str] = {}
        self.yaml_url: str = ""

    def as_dict(self):
        return {
            "name": self.name,
            "qcow2_url": self.qcow2_url,
            "meta": self.meta,
            "yaml_url": self.yaml_url,
        }

    def __repr__(self):
        return dedent(
            f"""
        Image={self.name}
          url={self.qcow2_url}
          meta={self.meta}
        """
        )


def get_fedora_images() -> list[Image]:
    def get(version) -> Image | None:
        base_url = f"https://download.fedoraproject.org/pub/fedora/linux/releases/{version}/Cloud/x86_64/images"
        resp = urllib3.request("GET", base_url, redirect=True)
        m = re.search(">(Fedora-Cloud.*?qcow2)<", resp.data.decode())
        if m:
            return Image(f"fedora-{version}", f"{base_url}/{m.group(1)}")

    return filter(lambda x: x, [get(v) for v in range(39, 60)])


def get_alpine_images() -> list[Image]:
    def get(version) -> Image | None:
        base_url = f"https://dl-cdn.alpinelinux.org/alpine/v{version}/releases/cloud"
        resp = urllib3.request("GET", base_url, redirect=True)
        m = re.findall(
            r"generic_alpine.*x86_64\-bios\-cloudinit-r0\.qcow2", resp.data.decode()
        )
        if m:
            image = Image(f"alpine-{version}", f"{base_url}/{m[-1]}")
            image.meta["username"] = "alpine"
            return image

    return filter(lambda x: x, [get(f"3.{v}") for v in range(20, 30)])


def get_freebsd_images() -> list[Image]:
    def releases():
        resp = urllib3.request(
            "GET",
            "https://download.freebsd.org/releases/VM-IMAGES/",
            redirect=True,
        )
        return re.findall(r'"(\d+\.\d-RELEASE)"', resp.data.decode())

    def base_url(release):
        return f"https://download.freebsd.org/releases/VM-IMAGES/{r}/amd64/Latest/"

    def file_names(release):
        resp = urllib3.request(
            "GET",
            base_url(release),
            redirect=True,
        )
        return re.findall(
            r">(FreeBSD-\d+\.\d-RELEASE-amd64-BASIC-CLOUDINIT-[uz]fs.qcow2.xz)<",
            resp.data.decode(),
        )

    for r in releases():
        for u in file_names(r):
            m = re.match(
                r"FreeBSD-(\d+\.\d)-RELEASE-amd64-BASIC-CLOUDINIT-(ufs|zfs).qcow2.xz", u
            )
            if m:
                name = f"freebsd-{m.group(1)}-{m.group(2)}"
                url = base_url(r) + u
                image = Image(name, url)
                image.meta["write_files"] = [
                    {
                        "content": (
                            "# Workaround for https://bugs.freebsd.org/bugzilla/show_bug.cgi?id=292137\n"
                            "nameserver 8.8.8.8\n"
                        ),
                        "owner": "root:root",
                        "path": "/etc/resolv.conf",
                        "permissions": "0644",
                        "append": True,
                    }
                ]
                image.meta["packages"] = ["sudo"]
                image.meta["groups"] = ["wheel"]
                yield image


def get_bsd_images() -> list[Image]:
    resp = urllib3.request(
        "GET",
        "https://raw.githubusercontent.com/goneri/bsd-cloud-image.org/refs/heads/main/src/images_data.json",
        redirect=True,
    )
    images: list[Image] = []
    for os in resp.json():
        for version in os["versions"]:
            for image_dict in version["images"]:
                name = f"{os['name']}-{version['name']}-{image_dict['flavor'].lower()}"
                image = Image(name, image_dict["url"])
                image.retrieve_metadata()

                python_interpreter = image_dict.get("python_interpreter")

                if python_interpreter:
                    image.meta["python_interpreter"] = python_interpreter

                images.append(image)
    return images


images: list[Image] = []

for name, qcow2_url in configuration.items():
    yaml_url = re.sub(r".qcow2", ".yaml", qcow2_url)
    if urllib3.request("HEAD", qcow2_url).status == 200:
        image = Image(name, qcow2_url)
        images.append(image)

images += get_fedora_images()
images += get_bsd_images()
images += get_alpine_images()
images += get_freebsd_images()

index_md = ""
images_redir = ""
for image in sorted(images, key=lambda i: i.name):
    images_redir += (
        f"    redir /images/{image.name}/{image.name}.qcow2 {image.qcow2_url}\n"
    )
    if image.yaml_url:
        images_redir += (
            f"    redir /images/{image.name}/{image.name}.yaml {image.yaml_url}\n"
        )
    index_md += f"- {image.name}\n"


index_md_file = Path("./images/index.md")
index_md_file.parent.mkdir(parents=True, exist_ok=True)
index_md_file.write_text(index_md)

images_json_file = Path("./virt-lightning.org/images.json")
images_json_file.write_text(json.dumps([i.as_dict() for i in images], indent=2))
