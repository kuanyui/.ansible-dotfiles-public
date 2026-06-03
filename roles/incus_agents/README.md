# roles/incus_agents

Per-project KVM VM launchers. One VM per `(agent, project)`.

Stronger isolation than `c-<agent>-<runtime>` rootless containers: separate kernel, virtio-fs share via standalone `virtiofsd`.

> [!IMPORTANT]
> Host-level concerns (which distros are supported, what gets installed on the host, the storage pool config matrix, CoW backends, openSUSE+snapper trap, moving the install tree, NAT vs bridge, virt-manager coexistence, `du` undercounting on loop-file pools) are all in [`roles/_incus_host_setup/README.md`](../_incus_host_setup/README.md). Those apply equally to this role and to `roles/incus_vm`.
>
> This file covers only what's specific to LLM agent VMs.

## Quick start

```sh
cd ~/project              # any project dir
v-claude init             # create VM + install claude (first time only, ~30-60s)
v-claude claude           # run claude inside the VM
v-claude shell            # zsh into the VM (cwd = /workspaces/<project>)
v-claude rma              # delete this VM
```

VM name = `v-<agent>-<projectname>`. Different projects get different VMs.

## What's inside the VM

- **Base**: Debian 13 minimal
- **Default shell**: zsh
- **apt packages** installed at `init`:
  - common: `openssh-server`, `curl`, `git`, `ca-certificates`, `sudo`, `zsh`, `zsh-syntax-highlighting`, `zsh-autosuggestions`, `tmux`
  - codex only: `nodejs`, `npm`
- **Agent binary**:
  - claude → `curl -fsSL https://claude.ai/install.sh | bash`
  - codex → `npm install -g @openai/codex`
- **Dotfiles**: `~/.bashrc`, `~/.zshrc`, `~/.tmux.conf` (rendered host-side at `apply-incus-agents` time, synced into the VM on every `init` - idempotent, so editing host dotfiles + re-`apply-incus-agents` + next `v-<agent> init` propagates changes into all VMs)
- **Your project dir**: virtio-fs shared at `/workspaces/<projectname>`. `shift=true` maps host UID 1000 ↔ VM UID 1000, so files appear as `user`, not `nobody`.

## How `v-claude init` works

1. Launcher reads `$PWD`, derives `PROJECT_NAME` and `VM_NAME` (`v-<agent>-<projectname>`)
2. If VM missing: `incus launch images:debian/13 <vm> --vm --config limits.cpu=4 --config limits.memory=4GiB --device root,size=10GiB`
3. Wait up to 90s for `incus-agent` inside the VM
4. Attach virtio-fs: host project dir → `/workspaces/<projectname>` (with `shift=true`)
5. apt install + create `user` (UID 1000) + chsh to zsh
6. `incus file push --recursive` staged dotfiles → `/home/user/`
7. Curl-install or npm-install the agent inside the VM
8. Done. Re-running `init` is idempotent.

## Where role-managed files live (host-side)

| What | Path |
|---|---|
| Launcher | `~/.local/bin/v-<agent>` |
| zsh completion | `~/.local/share/ansible-managed/incus-agents/zsh-completions/_v-<agent>` |
| bash completion | `~/.local/share/ansible-managed/incus-agents/bash-completions/v-<agent>` |
| Install manifest | `~/.local/share/ansible-managed/incus-agents/incus-apps.manifest.yml` |
| Staged VM dotfiles | `~/.local/share/ansible-managed/incus-agents/vm-rootfs/home/user/` (user variant) + `.../vm-rootfs/root/` (root variant) |

For Incus-level paths (cached images, VM disks, pool blocks under each storage config, snapshot locations): see [Where do cached incus images... live](../_incus_host_setup/README.md#where-do-cached-incus-images-per-vm-disk-files-installer-isos-and-snapshots-live-can-the-paths-be-changed) in `_incus_host_setup` README.

## Snapshots

This role does NOT auto-snapshot. Use Incus directly:

```sh
incus snapshot create v-claude-foo before-update
incus snapshot list v-claude-foo
incus snapshot restore v-claude-foo before-update
incus snapshot delete v-claude-foo before-update
```

Snapshot cost depends on storage pool backend - see [Snapshots backend cost matrix](../_incus_host_setup/README.md#snapshots---backend-cost-matrix).

## Resyncing dotfiles into existing VMs

If you edit `roles/dotfiles/templates/.bashrc.j2` or `roles/zsh/templates/.zshrc.j2` and re-run `make apply-incus-agents`, the host-side staging dir gets refreshed. To push the new dotfiles into every existing `v-*` VM without re-running `init` on each one:

```sh
make resync-incus-agents-dotfiles
```

(Non-destructive: just runs `incus file push --recursive --uid 1000 --gid 1000` from the staging dir into every VM. VM home content, agent state, tmux sessions, uncommitted work all untouched.)

Alternatively, on next `v-<agent> init` / `v-<agent> claude` / `v-<agent> shell` on any individual VM, the launcher pushes fresh dotfiles automatically.

## Cleanup

| What | Command |
|---|---|
| One VM | `v-<agent> rma` |
| Remove launchers + manifest (leaves VMs intact) | `make unapply-incus-agents` |

For host-level cleanup (cached images, nuke everything): see [Cleanup in `_incus_host_setup` README](../_incus_host_setup/README.md#cleanup-host-level).
