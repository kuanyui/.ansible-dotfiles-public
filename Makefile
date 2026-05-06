PLAYBOOK := ansible-playbook
PLAYBOOKS := playbooks

.PHONY: apply-user apply-root apply-all unstow check-user check-root check-all pull help

help:
	@echo "Targets:"
	@echo "  apply-user   Deploy user/ dotfiles to current user home (no sudo)"
	@echo "  apply-root   Deploy root/ dotfiles to /root          (needs sudo)"
	@echo "  apply-all    Both of the above"
	@echo "  unstow       Remove existing stow symlinks from ~/ and /root"
	@echo "  check-user   Dry-run diff for user dotfiles"
	@echo "  check-root   Dry-run diff for root dotfiles"
	@echo "  check-all    Dry-run diff for both"
	@echo "  pull         Reset hard to origin/master (destructive, requires confirmation)"

apply-user:
	$(PLAYBOOK) $(PLAYBOOKS)/user.yml

apply-root:
	$(PLAYBOOK) -K $(PLAYBOOKS)/root.yml

apply-all:
	$(PLAYBOOK) -K $(PLAYBOOKS)/all.yml

unstow:
	$(PLAYBOOK) -K $(PLAYBOOKS)/unstow.yml

check-user:
	$(PLAYBOOK) --check --diff $(PLAYBOOKS)/user.yml

check-root:
	$(PLAYBOOK) --check --diff -K $(PLAYBOOKS)/root.yml

check-all:
	$(PLAYBOOK) --check --diff -K $(PLAYBOOKS)/all.yml

pull:
	@echo "This will run: git fetch origin && git reset --hard origin/master"
	@git fetch origin
	@git diff --stat HEAD origin/master
	@if git diff --quiet HEAD origin/master; then \
		echo "Already up to date, nothing to do."; \
	else \
		echo ""; \
		echo "WARNING: The above changes will be discarded from your local tree."; \
		read -r -p "Type 'yes' to continue: " ans; \
		if [ "$$ans" = "yes" ]; then \
			git reset --hard origin/master; \
			echo "Done."; \
		else \
			echo "Aborted."; \
			exit 1; \
		fi \
	fi
