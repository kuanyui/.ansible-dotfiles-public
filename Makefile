PLAYBOOK := ansible-playbook
PLAYBOOKS := playbooks

.PHONY: apply-user apply-root apply-all-users apply-podman-oci-runtimes apply-container-apps apply-incus-vm apply-apparmor unstow check-user check-root check-all-users check-podman-oci-runtimes check-container-apps check-incus-vm check-apparmor unapply-podman-oci-runtimes unapply-container-apps unapply-incus-vm teardown-incus-host incus-overwrite-dotfiles-in-all-guest aa-notify-snapshot aa-notify-watch aa-log-watch aa-log-recent sandbox-user sandbox-root sandbox-container-apps sandbox-incus-vm sandbox-podman-oci-runtimes sandbox-apparmor sandbox-clean pull pull--amended help

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

apply-podman-oci-runtimes:  ## Provision crun + libkrun ,assert crun has `+LIBKRUN`, write `containers.conf` (optional), assert `podman info` shows krun active
	$(PLAYBOOK) --diff --ask-become-pass $(PLAYBOOKS)/podman_oci_runtimes.yml

unapply-podman-oci-runtimes:  ## Revert podman to distro default runtime (deletes the managed containers.conf; leaves installed libkrun packages alone)
	$(PLAYBOOK) --diff --ask-become-pass -e podman_runtime=default $(PLAYBOOKS)/podman_oci_runtimes.yml

apply-container-apps:  ## Install c-<template>-<runtime> launchers into ~/.local/bin/ (bypasses `setup_container_apps` gate)
	$(PLAYBOOK) --diff $(PLAYBOOKS)/container_apps.yml

unapply-container-apps:  ## Uninstall container_apps (reads ~/.local/share/container-templates/.ansible-manifest.yml, removes everything it recorded)
	$(PLAYBOOK) --diff $(PLAYBOOKS)/container_apps_uninstall.yml

incus-overwrite-dotfiles-in-all-guest:  ## Re-push staged dotfiles to all our managed Linux Incus guests. Run `apply-incus-vm` first; this only pushes, does not re-render. (Per-VM alternative: `ivm overwrite-dotfiles`.)
	@set -e; \
	WORKS="$$HOME/.local/share/ansible-managed/incus-vm/ivm/rootfs/Debian"; \
	if [ -d "$$WORKS/home/user" ] && [ -d "$$WORKS/root" ]; then SRC="$$WORKS"; \
	else echo "No staged dotfiles found -- run 'make apply-incus-vm' first" >&2; exit 1; fi; \
	echo "Source (Debian tree; the only buildable guest family today): $$SRC"; \
	VMS=$$(incus list user.ansible-managed=true --format csv --columns nt | awk -F, 'toupper($$2) ~ /VIRTUAL/ {print $$1}'); \
	if [ -z "$$VMS" ]; then echo "No v-* VMs found, nothing to do."; exit 0; fi; \
	for vm in $$VMS; do \
	    os=$$(incus config get "$$vm" user.ansible-guest-os 2>/dev/null || true); \
	    if [ "$$os" = "windows" ]; then echo "==> Skipping $$vm (guest-os=windows)"; continue; fi; \
	    echo "==> Re-pushing dotfiles into $$vm (user + root)"; \
	    incus file push --recursive --create-dirs --uid 1000 --gid 1000 "$$SRC/home/user" "$$vm/home/"; \
	    incus file push --recursive --create-dirs --uid 0 --gid 0 "$$SRC/root" "$$vm/"; \
	done

apply-incus-vm:  ## Install the `ivm` Incus VM launcher via `roles/incus_vm` (bypasses `setup_incus_vm` gate). Auto-installs incus + initializes via preseed when missing; --ask-become-pass needed only when those steps actually fire.
	$(PLAYBOOK) --diff --ask-become-pass $(PLAYBOOKS)/incus_vm.yml

unapply-incus-vm:  ## Uninstall `ivm` + the role's `~/.local/share/ansible-managed/incus-vm/` subdir ONLY; leaves the host incus daemon, storage pool, networks, VMs + snapshots, and your `incus` group untouched. For host-level teardown use `teardown-incus-host` (or pass `-e incus_vm_uninstall_*=true` toggles here; see roles/incus_vm/defaults/main/incus_host_uninstall.yml).
	$(PLAYBOOK) --diff $(PLAYBOOKS)/incus_vm_uninstall.yml

## Flags for `teardown-incus-host`. Default = every destructive `incus_vm_uninstall_*` step EXCEPT removing you from the `incus` group (so no re-login). Override to customize (e.g. add `-e incus_vm_uninstall_remove_user_from_incus_group=true`).
INCUS_VM_HOST_TEARDOWN_FLAGS := -e incus_vm_uninstall_delete_all_instances=true -e incus_vm_uninstall_delete_autocreated_user_projects=true -e incus_vm_uninstall_delete_incusbr0_network=true -e incus_vm_uninstall_delete_default_storage_pool=true -e incus_vm_uninstall_disable_incus_daemon_and_socket=true -e incus_vm_uninstall_revert_firewalld_incusbr0_zone=true

teardown-incus-host:  ## DESTRUCTIVE host-level incus teardown via `roles/incus_vm` (`incus_vm_state: absent` + `INCUS_VM_HOST_TEARDOWN_FLAGS`): deletes ALL incus VMs, the `default` storage pool (ERASES VM disks), `incusbr0`, incus-user's `user-*` projects + `incusbr-*` bridges, and stops+disables the incus daemon. KEEPS distro packages + your `incus` group membership (no re-login). Needs `--ask-become-pass`.
	$(PLAYBOOK) --diff --ask-become-pass $(PLAYBOOKS)/incus_vm_uninstall.yml $(INCUS_VM_HOST_TEARDOWN_FLAGS)

apply-apparmor:  ## Deploy AppArmor profiles for desktop GUI apps (Firefox / Chromium / VLC / mpv / VSCode / Telegram / etc.). Two phases: (1) a fast Python pre-flight does `python3-jsonschema` probe/install + `personal_dirs.yml` schema-validate + colored preview + y/N confirm, all BEFORE ansible-playbook starts so you do not have to wait for ansible to spin up just to be prompted; (2) only on `y` does ansible run, with `apparmor_non_interactive=true` to skip the now-redundant in-playbook validate/preview/confirm. Asks for the BECOME password up-front (`--ask-become-pass`) because ansible's default sudo invocation uses `-n` (non-interactive) which fails without a piped password. Bypasses `setup_apparmor` gate.
	python3 roles/apparmor/scripts/gen_personal_dirs_aa_mixins.py --confirm
	$(PLAYBOOK) --diff --ask-become-pass -e apparmor_non_interactive=true $(PLAYBOOKS)/apparmor.yml

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

check-incus-vm:  ## Dry-run diff for incus workstation launcher install
	$(PLAYBOOK) --check --diff $(PLAYBOOKS)/incus_vm.yml

check-apparmor:  ## Dry-run diff for AppArmor profile deployment
	$(PLAYBOOK) --check --diff --ask-become-pass $(PLAYBOOKS)/apparmor.yml

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

sandbox-incus-vm:  ## Dry-run `apply-incus-vm` (`ivm` install; `incus` binary stubbed) in a throwaway podman+systemd sandbox
	python3 scripts/sandbox/sandbox.py --runtime $(SANDBOX_RUNTIME) incus_vm

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
