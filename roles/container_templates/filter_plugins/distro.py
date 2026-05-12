"""Ansible filters for inferring distro family and OBS repo name from a
container image tag. Ported verbatim from the legacy `render_j2.py`'s
`ContainerConfig.distro` and `ContainerConfig.obs_repo_name` properties so
that templates render byte-identically after migration.
"""

from typing import Optional


def distro(image_name: str) -> Optional[str]:
    low = image_name.lower()
    if 'debian' in low or 'ubuntu' in low:
        return 'debian'
    if 'alpine' in low:
        return 'alpine'
    if 'suse' in low:    # 'opensuse/leap', 'opensuse/tumbleweed'
        return 'suse'
    if any(x in low for x in ['fedora', 'rocky', 'centos']):
        return 'redhat'
    return None


def obs_repo_name(image_name: str) -> str:
    low = image_name.lower()
    if 'debian:' in low:
        return image_name.replace('debian:', 'Debian_')
    if 'ubuntu:' in low:
        return image_name.replace('ubuntu:', 'xUbuntu_')
    if 'tumbleweed' in low:
        return 'openSUSE_Tumbleweed'
    if 'slowroll' in low:
        return 'openSUSE_Slowroll'
    if 'leap:' in low:
        return image_name.split(':')[1]
    if any(x in low for x in ['fedora', 'rocky', 'centos']):
        return image_name.capitalize().replace(':', '_')
    return ''


class FilterModule:
    def filters(self):
        return {
            'distro': distro,
            'obs_repo_name': obs_repo_name,
        }
