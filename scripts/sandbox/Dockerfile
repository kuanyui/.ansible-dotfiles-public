# Sandbox base image: Debian + tini + sshd + ansible-core.
#
# Why no systemd: libkrun's microVM design runs the container's CMD as a
# non-root user. systemd (when invoked as system manager) requires PID 1 +
# UID 0 and exits with "Explicit --user argument required to run as user
# manager." otherwise. crun/runc don't have this constraint but we want the
# sandbox image to work uniformly across `--runtime krun | crun | runc |
# system`, so we sidestep systemd entirely.
#
# What replaces it:
#   - `tini` is PID 1 (proper signal forwarding + zombie reaping)
#   - `sshd -D -e` is the workload (foreground, log to stderr)
#   - any in-container task that would `systemctl ...` gets a dummy stub from
#     the per-config `dummy_commands` list (apparmor config already stubs this).
#
# Built by scripts/sandbox/sandbox.py with:
#   podman build --build-arg SSH_AUTHORIZED_KEY="$(cat ~/.cache/.../ssh_key.pub)" ...
# then run with:
#   podman run --runtime krun --publish 127.0.0.1::22 ...

FROM --platform=linux/amd64 debian:trixie

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install --yes --no-install-recommends \
        openssh-server \
        tini \
        sudo \
        python3 python3-apt ansible-core \
        ca-certificates \
        tar gzip \
    && rm -rf /var/lib/apt/lists/*

# Generate sshd host keys at build time. (The Debian postinst would normally
# do this on service start via the systemd unit; we don't have systemd, so
# do it explicitly here.) Also ensure /run/sshd exists - sshd refuses to
# start without it.
RUN ssh-keygen -A && mkdir -p /run/sshd

# Sandbox user with passwordless sudo. The playbook runs as this user
# (matching the typical real-host workflow).
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

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/sbin/sshd", "-D", "-e"]
