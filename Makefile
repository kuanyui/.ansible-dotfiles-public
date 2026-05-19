PLAYBOOK := ansible-playbook
PLAYBOOKS := playbooks

.PHONY: apply-user apply-root apply-all-users apply-podman-runtime apply-container-apps apply-apparmor unstow check-user check-root check-all-users check-podman-runtime check-container-apps check-apparmor unapply-podman-runtime unapply-container-apps aa-notify-snapshot aa-notify-watch aa-log-watch aa-log-recent sandbox-apparmor sandbox-clean pull pull--amended help

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
	$(PLAYBOOK) $(PLAYBOOKS)/user.yml

apply-root:  ## Provision root (packages + zsh + emacs + dotfiles; needs sudo)
	$(PLAYBOOK) --ask-become-pass $(PLAYBOOKS)/root.yml

apply-all-users:  ## Provision both current user and root (i.e. `apply-user` + `apply-root`)
	$(PLAYBOOK) --ask-become-pass $(PLAYBOOKS)/all.yml

apply-podman-runtime:  ## Provision crun + libkrun ,assert crun has `+LIBKRUN`, write `containers.conf` (optional), assert `podman info` shows krun active
	$(PLAYBOOK) --ask-become-pass $(PLAYBOOKS)/podman.yml

unapply-podman-runtime:  ## Revert podman to distro default runtime (deletes the managed containers.conf; leaves installed libkrun packages alone)
	$(PLAYBOOK) --ask-become-pass -e podman_runtime=default $(PLAYBOOKS)/podman.yml

apply-container-apps:  ## Install c-<template>-<runtime> launchers into ~/.local/bin/ (bypasses `setup_container_apps` gate)
	$(PLAYBOOK) $(PLAYBOOKS)/container_apps.yml

unapply-container-apps:  ## Uninstall container_apps (reads ~/.local/share/container-templates/.ansible-manifest.yml, removes everything it recorded)
	$(PLAYBOOK) $(PLAYBOOKS)/container_apps_uninstall.yml

apply-apparmor:  ## Deploy AppArmor profiles for desktop GUI apps (Firefox / Chromium / VLC / mpv / VSCode / Telegram / etc.); requires `roles/apparmor/local_vars/deny_personal_dirs.aa` (see scripts/gen_deny_personal_dirs.py); bypasses `setup_apparmor` gate
	@test -f roles/apparmor/local_vars/deny_personal_dirs.aa || { \
		echo "ERROR: roles/apparmor/local_vars/deny_personal_dirs.aa not found."; \
		echo "Run: python3 scripts/gen_deny_personal_dirs.py <path> [<path> ...]"; \
		exit 1; \
	}
	python3 scripts/check_deny_personal_dirs.py
	@printf 'Proceed with apply? [y/N] '; read answer; \
	case "$$answer" in \
		[Yy]) ;; \
		*) echo "Aborted."; exit 1 ;; \
	esac
	$(PLAYBOOK) --ask-become-pass --diff $(PLAYBOOKS)/apparmor.yml

### -------------------------------------------------------------------------
### Dry-run (--check --diff)
### -------------------------------------------------------------------------

check-user:  ## Dry-run diff for current user provisioning
	$(PLAYBOOK) --check --diff $(PLAYBOOKS)/user.yml

check-root:  ## Dry-run diff for root provisioning
	$(PLAYBOOK) --check --diff --ask-become-pass $(PLAYBOOKS)/root.yml

check-all-users:  ## Dry-run diff for both user and root (i.e. `check-user` + `check-root`)
	$(PLAYBOOK) --check --diff --ask-become-pass $(PLAYBOOKS)/all.yml

check-podman-runtime:  ## Dry-run diff for podman OCI runtime config
	$(PLAYBOOK) --check --diff --ask-become-pass $(PLAYBOOKS)/podman.yml

check-container-apps:  ## Dry-run diff for container_apps install
	$(PLAYBOOK) --check --diff $(PLAYBOOKS)/container_apps.yml

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
### Sandbox dry-run (rootless podman + systemd + sshd; default --runtime krun)
### -------------------------------------------------------------------------

# Default runtime is `crun` so systemd can run as PID 1 (libkrun rejects this -
# see scripts/sandbox/Dockerfile rationale). Override per invocation:
#   make sandbox-apparmor SANDBOX_RUNTIME=runc
#   make sandbox-apparmor SANDBOX_RUNTIME=system  # use podman's configured default
SANDBOX_RUNTIME ?= crun

# Note on AppArmor: rootless podman cannot set `--security-opt apparmor=<X>`
# (CAP_MAC_ADMIN required). The sandbox container relies on user-namespace +
# default-seccomp + cap-drop NET_RAW for Layer 2 hardening. For stronger
# isolation (own kernel), switch the sandbox runtime to Kata Containers.

sandbox-apparmor:  ## Dry-run `apply-apparmor` in a throwaway podman+systemd sandbox; streams diff + runs `apparmor_parser --skip-kernel-load` post-check
	python3 scripts/sandbox/sandbox.py --runtime $(SANDBOX_RUNTIME) apparmor

sandbox-clean:  ## Remove the cached sandbox base image to free disk (running sandbox containers are auto-removed after each run)
	podman rmi localhost/ansible-dotfiles-sandbox:latest 2>/dev/null || true

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
