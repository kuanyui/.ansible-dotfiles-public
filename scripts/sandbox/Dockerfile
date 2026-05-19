# Sandbox base image: Debian + systemd + sshd + ansible-core.
#
# Built by scripts/sandbox/sandbox.py before each run with:
#   podman build --build-arg SSH_AUTHORIZED_KEY="$(cat ~/.cache/.../ssh_key.pub)" ...
# then run with:
#   podman run --runtime krun --systemd=always --publish 0:22 ...
# so sandbox.py reaches the container via ssh -p <random_host_port> sandboxuser@127.0.0.1.
#
# We keep this image deliberately minimal - any playbook-specific packages
# (apparmor, libkrun1, etc) are installed inside the running container by the
# SandboxConfig's `extra_packages_apt` field, not baked here. That way one
# image is reusable across all sandbox configs.

FROM --platform=linux/amd64 debian:trixie

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install --yes --no-install-recommends \
        systemd systemd-sysv \
        openssh-server \
        sudo \
        python3 python3-apt ansible-core \
        ca-certificates \
        tar gzip \
    && rm -rf /var/lib/apt/lists/*

RUN systemctl enable ssh

# Sandbox user with passwordless sudo. The playbook runs as this user (matching
# the typical real-host workflow: a regular user invoking ansible-playbook
# --ask-become-pass against localhost).
RUN useradd --create-home --shell /bin/bash sandboxuser && \
    echo 'sandboxuser ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/sandboxuser && \
    chmod 440 /etc/sudoers.d/sandboxuser

# SSH_AUTHORIZED_KEY is passed via --build-arg from the host so the harness's
# private key can ssh in. See sandbox.py's `_ensure_ssh_key` (key at
# ~/.cache/ansible-dotfiles-sandbox/ssh_key{,.pub}).
ARG SSH_AUTHORIZED_KEY=""
RUN mkdir -p /home/sandboxuser/.ssh && \
    echo "$SSH_AUTHORIZED_KEY" > /home/sandboxuser/.ssh/authorized_keys && \
    chown -R sandboxuser:sandboxuser /home/sandboxuser/.ssh && \
    chmod 700 /home/sandboxuser/.ssh && \
    chmod 600 /home/sandboxuser/.ssh/authorized_keys

STOPSIGNAL SIGRTMIN+3
CMD ["/usr/lib/systemd/systemd"]
