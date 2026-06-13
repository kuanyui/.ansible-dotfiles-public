PLAYBOOK := ansible-playbook
PLAYBOOKS := playbooks

.PHONY: help unstow apply-user apply-root apply-all-users apply-podman-oci-runtimes unapply-podman-oci-runtimes apply-container-apps unapply-container-apps apply-apparmor apply-trusted-pubkeys apply-firefox-tunes apply-mpv vm-incus-install vm-incus-check vm-incus-sandbox vm-incus-uninstall-ivm vm-incus-teardown-host vm-incus-push-dotfiles vm-quickemu-install vm-quickemu-check vm-quickemu-uninstall-qvm check-user check-root check-all-users check-podman-oci-runtimes check-container-apps check-apparmor check-trusted-pubkeys check-firefox-tunes check-mpv aa-notify-snapshot aa-notify-watch aa-log-watch aa-log-recent sandbox-user sandbox-root sandbox-container-apps sandbox-podman-oci-runtimes sandbox-apparmor sandbox-clean pull pull--amended

### -------------------------------------------------------------------------
### Basic
### -------------------------------------------------------------------------

help:     ## Show this self-documented help message.
	@# Some operating system / Linux distro may use `mawk` (e.g. Ubuntu), so prefer more portable `perl` over `awk`.
	@export S=`basename $${SHELL}`; if [ $${S} != "zsh" ] && [ $${S} != "fish" ]; then echo "(Tip: You are using \`$${S}\`, but you can consider to use \`zsh\` or \`fish\` because they support tab compoletions for Makefile targets & variables.)"; fi

	@if command -v perl >/dev/null 2>&1; then \
	        printf "\033[36m=============================================================\033[0m\n" ; \
	        printf "\033[36m Variables                                                   \033[0m\n" ; \
	        printf "\033[36m=============================================================\033[0m\n" ; \
	        perl -ne 'if (/^## /) { $$comment = $$_; $$next = <>; if ($$next =~ /^([A-Za-z0-9_]+)\s*[:?+]?=\s*(.*)$$/) { printf "\033[35m%-30s\033[0m %s", $$1, substr($$comment, 3); } }' $(MAKEFILE_LIST); \
	        printf "\n"; \
	        printf "\033[36m=============================================================\033[0m\n" ; \
	        printf "\033[36m Targets                                                     \033[0m\n" ; \
	        printf "\033[36m=============================================================\033[0m\n" ; \
	        perl -ne 'if (/^([a-zA-Z0-9_-]+):.*?## (.*)$$/) { printf "\033[32m%-30s\033[0m %s\n", $$1, $$2; } elsif (/^[ \t]*### *(.*)/) { print "\033[34m$$1\033[0m\n"; }' $(MAKEFILE_LIST); \
	else \
	        printf "\033[36m=============================================================\033[0m\n" ; \
	        printf "\033[36m Variables                                                   \033[0m\n" ; \
	        printf "\033[36m=============================================================\033[0m\n" ; \
	        gawk '/^## /{comment=$$0; getline; if ($$1 ~ /^[A-Za-z0-9_]+$$/ && match($$0, /^[^:?+]*[:?+]?=/, m)) printf "\033[35m%-30s\033[0m %s\n", $$1, substr(comment, 4)}' $(MAKEFILE_LIST) ; \
	        printf "\n"; \
	        printf "\033[36m=============================================================\033[0m\n" ; \
	        printf "\033[36m Targets                                                     \033[0m\n" ; \
	        printf "\033[36m=============================================================\033[0m\n" ; \
	        gawk 'match($$0, /^([a-zA-Z0-9_-]+):.*?## (.*)$$/, m){printf "\033[32m%-30s\033[0m %s\n", m[1], m[2]} match($$0, /^[ \\t]*### *(.*)/, m){printf "\033[34m%s\033[0m\n", m[1]}' $(MAKEFILE_LIST); \
	fi

unstow:  ## [Legacy] Remove existing stow symlinks from ~/ and /root
	$(PLAYBOOK) -K $(PLAYBOOKS)/unstow.yml

### -------------------------------------------------------------------------
### Apply playbooks
### -------------------------------------------------------------------------


apply-user:  ## Provision current user (zsh + emacs + dotfiles)
	$(PLAYBOOK) --diff $(PLAYBOOKS)/user.yml

apply-root:  ## Provision root (distro_packages + zsh + emacs + dotfiles; needs sudo)
	$(PLAYBOOK) --diff --ask-become-pass $(PLAYBOOKS)/root.yml

apply-all-users:  ## Provision both current user and root (i.e. `apply-user` + `apply-root`)
	$(PLAYBOOK) --diff --ask-become-pass $(PLAYBOOKS)/all.yml

apply-podman-oci-runtimes:  ## Provision crun + libkrun, assert crun has `+LIBKRUN`, write `containers.conf`, assert `podman info` shows krun active
	$(PLAYBOOK) --diff --ask-become-pass $(PLAYBOOKS)/podman_oci_runtimes.yml

unapply-podman-oci-runtimes:  ## Revert podman to distro default runtime (deletes the managed containers.conf; leaves installed libkrun packages alone)
	$(PLAYBOOK) --diff --ask-become-pass -e podman_runtime=default $(PLAYBOOKS)/podman_oci_runtimes.yml

apply-container-apps:  ## Install c-<template>-<runtime> launchers into ~/.local/bin/ (bypasses `setup_container_apps` gate)
	$(PLAYBOOK) --diff $(PLAYBOOKS)/container_apps.yml

unapply-container-apps:  ## Uninstall container_apps (reads ~/.local/share/container-templates/.ansible-manifest.yml, removes everything it recorded)
	$(PLAYBOOK) --diff $(PLAYBOOKS)/container_apps_uninstall.yml

apply-apparmor:  ## Deploy AppArmor profiles for desktop GUI apps (Firefox / Chromium / VLC / VSCode / etc.; bypasses `setup_apparmor` gate). Python pre-flight validates + previews + asks y/N before ansible runs. Needs sudo.
	python3 roles/apparmor/scripts/gen_personal_dirs_aa_mixins.py --confirm
	$(PLAYBOOK) --diff --ask-become-pass -e apparmor_non_interactive=true $(PLAYBOOKS)/apparmor.yml

apply-trusted-pubkeys:  ## Pin GitHub/GitLab SSH host keys (~/.ssh/known_hosts) + Debian CD signing keys (dedicated GPG keyring) for the current user (bypasses `setup_trusted_pubkeys` gate). Idempotent; user-level, no sudo.
	$(PLAYBOOK) --diff $(PLAYBOOKS)/trusted_pubkeys.yml

apply-firefox-tunes:  ## Apply Firefox about:config tweaks (session-store interval + cache off the SSD) to every profile of the current user (bypasses `setup_firefox_tunes` gate). Writes user.js per profile; restart Firefox to apply. No sudo.
	$(PLAYBOOK) --diff $(PLAYBOOKS)/firefox_tunes.yml

apply-mpv:  ## Deploy mpv config (mpv.conf with `vo=wlshm` + input.conf + Lua scripts) to ~/.config/mpv/ (bypasses `setup_mpv` gate). Refuses to overwrite legacy stow symlinks. No sudo.
	$(PLAYBOOK) --diff $(PLAYBOOKS)/mpv.yml

### -------------------------------------------------------------------------
### Incus (host daemon + the `ivm` VM launcher)
### -------------------------------------------------------------------------

## Incus storage pool backend (available: dir|btrfs|zfs|lvm-thin, default: `btrfs`). Details: roles/vm_incus/defaults/main/incus_host_install.yml
INCUS_STORAGE_POOL_DRIVER ?=
## Incus storage pool source path (default: `/home/incus-storage.img`). Details: roles/vm_incus/defaults/main/incus_host_install.yml
INCUS_STORAGE_POOL_SOURCE ?=
## Incus storage pool size; empty for `dir` (default: `500GiB`). Details: roles/vm_incus/defaults/main/incus_host_install.yml
INCUS_STORAGE_POOL_SIZE ?=

# Which of the three INCUS_STORAGE_POOL_* the user actually set (origin = command
# line / environment) -> passed through to ansible as `-e` only for those (validation,
# the storage-layout preview, and the first-time confirm now all live in the role:
# roles/vm_incus/tasks/incus_host_install.yml).
_pool_drv_set  := $(filter command line environment,$(origin INCUS_STORAGE_POOL_DRIVER))
_pool_src_set  := $(filter command line environment,$(origin INCUS_STORAGE_POOL_SOURCE))
_pool_size_set := $(filter command line environment,$(origin INCUS_STORAGE_POOL_SIZE))
# True (non-empty) when the user set ANY of the three -> the role then knows the
# storage layout was EXPLICITLY requested (vs a plain reconcile run using defaults),
# so it can FAIL loudly - not just warn - if a pre-existing `default` pool means the
# override can't apply (see tasks/incus_host_install.yml).
_pool_any_set  := $(or $(_pool_drv_set),$(_pool_src_set),$(_pool_size_set))

# -> ansible `-e` only for vars the user set; unset defers to the role's
# defaults/main (no Makefile-side default to drift). An explicit-but-empty value
# (`INCUS_STORAGE_POOL_SIZE=` for `dir`) still counts as set -> `-e ...size=` (= no size).
_incus_storage_overrides := \
  $(if $(_pool_drv_set),-e incus_storage_pool_driver=$(INCUS_STORAGE_POOL_DRIVER)) \
  $(if $(_pool_src_set),-e incus_storage_pool_source=$(INCUS_STORAGE_POOL_SOURCE)) \
  $(if $(_pool_size_set),-e incus_storage_pool_size=$(INCUS_STORAGE_POOL_SIZE)) \
  $(if $(_pool_any_set),-e incus_storage_pool_overrides_passed=true)

vm-incus-install:  ## Set up the incus host (daemon, `default` pool, `incusbr0`, `incus` group) + install the `ivm` launcher (`roles/vm_incus`; bypasses `setup_vm_incus` gate). On first-time init the role confirms the storage pool layout before `incus admin init` (skipped once a `default` pool exists). Sudo only for the host steps that actually run.
	$(PLAYBOOK) --diff --ask-become-pass $(PLAYBOOKS)/vm_incus.yml $(_incus_storage_overrides)

vm-incus-push-dotfiles:  ## Re-push staged dotfiles to all managed Incus guests (run `vm-incus-install` first; pushes only, no re-render). Per-VM: `ivm overwrite-dotfiles`.
	@set -e; \
	WORKS="$$HOME/.local/share/ansible-managed/vm-incus/ivm/rootfs/Debian"; \
	if [ -d "$$WORKS/home/user" ] && [ -d "$$WORKS/root" ]; then SRC="$$WORKS"; \
	else echo "No staged dotfiles found -- run 'make vm-incus-install' first" >&2; exit 1; fi; \
	echo "Source (Debian tree; the only buildable guest family today): $$SRC"; \
	VMS=$$(incus list user.ansible_managed=true --format csv --columns nt | awk -F, 'toupper($$2) ~ /VIRTUAL/ {print $$1}'); \
	if [ -z "$$VMS" ]; then echo "No v-* VMs found, nothing to do."; exit 0; fi; \
	for vm in $$VMS; do \
	    os=$$(incus config get "$$vm" user.ivm_guest_os 2>/dev/null || true); \
	    if [ "$$os" = "windows" ]; then echo "==> Skipping $$vm (guest-os=windows)"; continue; fi; \
	    echo "==> Re-pushing dotfiles into $$vm (user + root)"; \
	    incus file push --recursive --create-dirs --uid 1000 --gid 1000 "$$SRC/home/user" "$$vm/home/"; \
	    incus file push --recursive --create-dirs --uid 0 --gid 0 "$$SRC/root" "$$vm/"; \
	done

vm-incus-uninstall-ivm:  ## Uninstall `ivm` + its `~/.local/share/ansible-managed/vm-incus/` subdir ONLY; leaves incus daemon, pool, networks, VMs, and your `incus` group intact. Host-level teardown: `vm-incus-teardown-host` (or `-e vm_incus_uninstall_*=true` here).
	$(PLAYBOOK) --diff $(PLAYBOOKS)/vm_incus_uninstall.yml

## Extra `-e vm_incus_uninstall_*=true` flags appended to `vm-incus-teardown-host` (default: none). e.g. ALSO leave the `incus` group (forces a re-login):  make vm-incus-teardown-host VM_INCUS_HOST_TEARDOWN_EXTRA="-e vm_incus_uninstall_remove_user_from_incus_group=true"
VM_INCUS_HOST_TEARDOWN_EXTRA ?=

## `vm-incus-teardown-host`'s ansible flags: every destructive `vm_incus_uninstall_*` step EXCEPT `incus` group removal, plus $(VM_INCUS_HOST_TEARDOWN_EXTRA). To customize, set that var above - don't edit this line.
VM_INCUS_HOST_TEARDOWN_FLAGS := -e vm_incus_uninstall_delete_all_instances=true -e vm_incus_uninstall_delete_autocreated_user_projects=true -e vm_incus_uninstall_delete_incusbr0_network=true -e vm_incus_uninstall_delete_default_storage_pool=true -e vm_incus_uninstall_disable_incus_daemon_and_socket=true -e vm_incus_uninstall_revert_firewalld_incusbr0_zone=true $(VM_INCUS_HOST_TEARDOWN_EXTRA)

vm-incus-teardown-host:  ## DESTRUCTIVE host-level incus teardown: deletes ALL VMs, the `default` pool (ERASES disks), `incusbr0`, `user-*` projects + `incusbr-*` bridges, and disables the daemon. Keeps packages + your `incus` group. Needs sudo.
	$(PLAYBOOK) --diff --ask-become-pass $(PLAYBOOKS)/vm_incus_uninstall.yml $(VM_INCUS_HOST_TEARDOWN_FLAGS)

vm-incus-check:  ## Dry-run `vm-incus-install` (`--check --diff`). Honors the same INCUS_STORAGE_POOL_* overrides.
	$(PLAYBOOK) --check --diff $(PLAYBOOKS)/vm_incus.yml $(_incus_storage_overrides)

vm-incus-sandbox:  ## Dry-run `vm-incus-install` in a throwaway podman+systemd sandbox (`incus` binary stubbed).
	python3 scripts/sandbox/sandbox.py --runtime $(SANDBOX_RUNTIME) vm_incus

### -------------------------------------------------------------------------
### Quickemu (the `qvm` launcher; desktop/Windows/macOS axis - roles/vm_quickemu)
### -------------------------------------------------------------------------

vm-quickemu-install:  ## Install quickemu host packages + the `qvm` launcher (`roles/vm_quickemu`; bypasses `setup_vm_quickemu` gate). Prebuilt tumbleweed/debian/fedora images = no interactive install. openSUSE hosts: `quickemu` itself is NOT packaged - the play warns with manual steps. Sudo only for package installs.
	$(PLAYBOOK) --diff --ask-become-pass $(PLAYBOOKS)/vm_quickemu.yml

vm-quickemu-check:  ## Dry-run `vm-quickemu-install` (`--check --diff`).
	$(PLAYBOOK) --check --diff --ask-become-pass $(PLAYBOOKS)/vm_quickemu.yml

vm-quickemu-uninstall-qvm:  ## Uninstall `qvm` + its `~/.local/share/ansible-managed/vm-quickemu/` subdir ONLY; VM data (`~/.local/share/qvm/`) and packages untouched.
	$(PLAYBOOK) --diff $(PLAYBOOKS)/vm_quickemu_uninstall.yml

### -------------------------------------------------------------------------
### Dry-run (--check --diff)
### -------------------------------------------------------------------------

check-user:  ## Dry-run diff for current user provisioning
	$(PLAYBOOK) --check --diff $(PLAYBOOKS)/user.yml

check-root:  ## Dry-run diff for root provisioning
	$(PLAYBOOK) --check --diff --ask-become-pass $(PLAYBOOKS)/root.yml

check-all-users:  ## Dry-run diff for both user and root (i.e. `check-user` + `check-root`)
	$(PLAYBOOK) --check --diff --ask-become-pass $(PLAYBOOKS)/all.yml

check-podman-oci-runtimes:  ## Dry-run diff for podman OCI runtime config
	$(PLAYBOOK) --check --diff --ask-become-pass $(PLAYBOOKS)/podman_oci_runtimes.yml

check-container-apps:  ## Dry-run diff for container_apps install
	$(PLAYBOOK) --check --diff $(PLAYBOOKS)/container_apps.yml

check-apparmor:  ## Dry-run diff for AppArmor profile deployment
	$(PLAYBOOK) --check --diff --ask-become-pass $(PLAYBOOKS)/apparmor.yml

check-trusted-pubkeys:  ## Dry-run diff for trusted_pubkeys (SSH host keys + Debian CD signing keys)
	$(PLAYBOOK) --check --diff $(PLAYBOOKS)/trusted_pubkeys.yml

check-firefox-tunes:  ## Dry-run diff for firefox_tunes (per-profile user.js)
	$(PLAYBOOK) --check --diff $(PLAYBOOKS)/firefox_tunes.yml

check-mpv:  ## Dry-run diff for mpv config deployment (~/.config/mpv/)
	$(PLAYBOOK) --check --diff $(PLAYBOOKS)/mpv.yml

### -------------------------------------------------------------------------
### AppArmor runtime helpers (live denial inspection)
### -------------------------------------------------------------------------

aa-notify-snapshot:  ## Snapshot of recent AppArmor denials via `aa-notify -s 1 -v`
	sudo aa-notify -s 1 -v

aa-notify-watch:  ## Tail AppArmor denials live via `aa-notify -p -w 5`
	sudo aa-notify -p -w 5

aa-log-watch:  ## Tail kernel AppArmor messages (auditd if present, else journalctl -k)
	@if systemctl is-active --quiet auditd; then \
		sudo tail -f /var/log/audit/audit.log; \
	else \
		sudo journalctl -k -f | grep --line-buffered -i apparmor; \
	fi

LOG_SINCE_SECS ?= 60
aa-log-recent:  ## Print recent AppArmor messages within `LOG_SINCE_SECS` (default 60) seconds
	@if systemctl is-active --quiet auditd; then \
		sudo ausearch -m AVC -ts $(shell date -d '$(LOG_SINCE_SECS) seconds ago' '+%m/%d/%Y') $(shell date -d '$(LOG_SINCE_SECS) seconds ago' '+%H:%M:%S') -i | grep -i apparmor || true; \
	else \
		sudo journalctl -k --since="$(LOG_SINCE_SECS) seconds ago" | grep -i apparmor || true; \
	fi

### -------------------------------------------------------------------------
### Sandbox dry-run (rootless podman + real systemd via crun; podman exec for
### tasks; image + container overlay both stored in tmpfs to avoid SSD wear)
### -------------------------------------------------------------------------

# Default runtime is `crun` so systemd can run as PID 1 (libkrun rejects this -
# see scripts/sandbox/Dockerfile rationale). Override per invocation:
#   make sandbox-apparmor SANDBOX_RUNTIME=runc
#   make sandbox-apparmor SANDBOX_RUNTIME=system  # use podman's configured default
## available: system, crun, runc (default: `crun`)
SANDBOX_RUNTIME ?= crun

# Note on AppArmor: rootless podman cannot set `--security-opt apparmor=<X>`
# (CAP_MAC_ADMIN required). The sandbox container relies on user-namespace +
# default-seccomp + cap-drop NET_RAW for Layer 2 hardening. For stronger
# isolation (own kernel), switch the sandbox runtime to Kata Containers.

# Note on storage: sandbox.py passes `--root /tmp/...` and `--runroot /tmp/...`
# to every podman call, so image cache + container overlay live in tmpfs (RAM)
# instead of `~/.local/share/containers/` (SSD). First run after reboot has to
# rebuild the image (~1-2 min on warm apt cache); subsequent runs reuse the
# tmpfs cache. `make sandbox-clean` wipes the tmpfs dirs.

sandbox-user:  ## Dry-run `apply-user` (zsh + emacs + dotfiles deploy) in a throwaway podman+systemd sandbox
	python3 scripts/sandbox/sandbox.py --runtime $(SANDBOX_RUNTIME) user

sandbox-root:  ## Dry-run `apply-root` (distro_packages + zsh + emacs + dotfiles, is_root=true) in a throwaway podman+systemd sandbox
	python3 scripts/sandbox/sandbox.py --runtime $(SANDBOX_RUNTIME) root

sandbox-container-apps:  ## Dry-run `apply-container-apps` (c-<template>-<runtime> launcher install) in a throwaway podman+systemd sandbox
	python3 scripts/sandbox/sandbox.py --runtime $(SANDBOX_RUNTIME) container_apps

sandbox-podman-oci-runtimes:  ## Dry-run `apply-podman-oci-runtimes` (containers.conf write; `crun` and `podman` are stubbed) in a throwaway podman+systemd sandbox
	python3 scripts/sandbox/sandbox.py --runtime $(SANDBOX_RUNTIME) podman_oci_runtimes

sandbox-apparmor:  ## Dry-run `apply-apparmor` in a throwaway podman+systemd sandbox; streams diff + runs `apparmor_parser --skip-kernel-load` post-check
	python3 scripts/sandbox/sandbox.py --runtime $(SANDBOX_RUNTIME) apparmor

sandbox-clean:  ## Wipe the sandbox's tmpfs storage (cached image + any leaked state). Reboot does this automatically.
	rm -rf /tmp/ansible-dotfiles-sandbox-storage /tmp/ansible-dotfiles-sandbox-run

### -------------------------------------------------------------------------
### Update this repo
### -------------------------------------------------------------------------

pull--amended:  ## Reset HEAD^^^, then pull (requires clean worktree - for squashing debug commits)
	@if git diff --quiet && git diff --cached --quiet; then \
	        echo "Worktree is clean - resetting HEAD^^^..."; \
	        git reset --hard HEAD^^^; \
	        $(MAKE) pull; \
	else \
	        echo "ERROR: Worktree is not clean. Commit or stash your changes first."; \
	        exit 1; \
	fi

pull:  ## Git reset hard to origin/master (destructive, requires confirmation)
	@git fetch origin
	@git --no-pager diff --stat master origin/master
	@if git diff --quiet master origin/master; then \
	        if ! git symbolic-ref HEAD > /dev/null 2>&1; then \
	                echo "master is up to date, but HEAD is detached - switching to master..."; \
	                git checkout master; \
	                echo "Done."; \
	        else \
	                echo "Already up to date, nothing to do."; \
	        fi; \
	elif git diff --quiet && git diff --cached --quiet; then \
	        echo "No changes in working tree, no staged changes in index - resetting without confirmation..."; \
	        git checkout master; \
	        git reset --hard origin/master; \
	        echo "Done."; \
	else \
	        echo ""; \
	        echo "WARNING: You have uncommitted changes in working tree or staging area that will be lost after reset."; \
	        read -r -p "Type 'yes' to continue: " ans; \
	        if [ "$$ans" = "yes" ]; then \
	                git checkout master; \
	                git reset --hard origin/master; \
	                echo "Done."; \
	        else \
	                echo "Aborted."; \
	                exit 1; \
	        fi \
	fi
