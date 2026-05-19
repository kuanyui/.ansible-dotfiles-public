# Sandbox base image: Debian + systemd + ansible-core.
#
# Why systemd as PID 1: realistic simulation. The role's handlers fire
# `systemctl reload apparmor` etc. for real, journald collects logs, etc.
# Works fine under `--runtime crun | runc | system` (default crun).
#
# Why NOT --runtime krun: libkrun's init.krun is hard-coded as PID 1 (kernel
# cmdline `init=/init.krun`); your CMD is fork'd as PID 2+. systemd refuses
# to run as system manager unless PID 1, so the container exits immediately.
# See:
#   https://github.com/containers/libkrun/blob/main/init/init.c
#   https://github.com/containers/libkrun/issues/223
# If you want microVM isolation AND systemd, you need Kata Containers, not
# libkrun.
#
# Container access: `podman exec` (no sshd in image). We don't need ssh-based
# exec because crun supports `podman exec` natively.

FROM --platform=linux/amd64 debian:trixie

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install --yes --no-install-recommends \
        systemd systemd-sysv \
        sudo \
        python3 python3-apt ansible-core \
        ca-certificates \
        tar gzip \
    && rm -rf /var/lib/apt/lists/*

# Sandbox user with passwordless sudo. The playbook runs as this user
# (matching the typical real-host workflow).
RUN useradd --create-home --shell /bin/bash sandboxuser && \
    echo 'sandboxuser ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/sandboxuser && \
    chmod 440 /etc/sudoers.d/sandboxuser

STOPSIGNAL SIGRTMIN+3
CMD ["/usr/lib/systemd/systemd"]
