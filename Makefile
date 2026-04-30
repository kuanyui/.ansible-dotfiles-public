PLAYBOOK := ansible-playbook
PLAYBOOKS := playbooks

.PHONY: apply-user apply-root apply-all unstow check-user check-root help

help:
	@echo "Targets:"
	@echo "  apply-user   Deploy user/ dotfiles to current user home (no sudo)"
	@echo "  apply-root   Deploy root/ dotfiles to /root          (needs sudo)"
	@echo "  apply-all    Both of the above"
	@echo "  unstow       Remove existing stow symlinks from ~/ and /root"
	@echo "  check-user   Dry-run diff for user dotfiles"
	@echo "  check-root   Dry-run diff for root dotfiles"

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
