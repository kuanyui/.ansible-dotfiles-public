PLAYBOOK := ansible-playbook
PLAYBOOKS := playbooks

.PHONY: apply-user apply-root apply-all unstow check-user check-root check-all pull pull--amended help

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


apply-user:  ## Deploy dotfiles to current user home (no sudo)
	$(PLAYBOOK) $(PLAYBOOKS)/user.yml

apply-root:  ## Deploy dotfiles to /root (needs sudo)
	$(PLAYBOOK) --ask-become-pass $(PLAYBOOKS)/root.yml

apply-all:  ## Deploy dotfiles for both current user and root
	$(PLAYBOOK) --ask-become-pass $(PLAYBOOKS)/all.yml

apply-podman:  ## Configure podman runtime (needs sudo for package install)
	$(PLAYBOOK) --ask-become-pass $(PLAYBOOKS)/podman.yml

### -------------------------------------------------------------------------
### Dry-run (--check --diff)
### -------------------------------------------------------------------------

check-user:  ## Dry-run diff for user dotfiles
	$(PLAYBOOK) --check --diff $(PLAYBOOKS)/user.yml

check-root:  ## Dry-run diff for root dotfiles
	$(PLAYBOOK) --check --diff --ask-become-pass $(PLAYBOOKS)/root.yml

check-all:  ## Dry-run diff for both user and root
	$(PLAYBOOK) --check --diff --ask-become-pass $(PLAYBOOKS)/all.yml

check-podman:  ## Dry-run diff for podman runtime config
	$(PLAYBOOK) --check --diff --ask-become-pass $(PLAYBOOKS)/podman.yml

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
