# Common Guidelines
<!-- https://github.com/multica-ai/andrej-karpathy-skills/blob/main/CLAUDE.md -->

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

# Project Guidelines

- NEVER commit in this project. Do not run `git commit` / `git add` / `git push`, and do not offer to. The user commits their own work, in their own batches. Make the file edits and stop; leave the working tree dirty for the user to review and commit. This holds even after large multi-file changes - do not treat "this is a lot of changes" as a reason to offer a commit.
- Task tracking: never rely on the in-session task tool (TaskCreate / TaskList) alone - it is local and ephemeral, so it does not survive across machines and is not git-tracked. Whenever you create or update tasks, also mirror them into a committed `TODO.md` (one line per task: status + short subject), so the task list is portable across computers and reviewable in the repo. The task tool is the working view; `TODO.md` is the durable source of truth - keep them in sync.
- All code content (comments, variable names, strings) must be in English.
- Variable names must be unambiguous on their own - the name alone must answer "X of what?". A bare noun that leaves the qualifier implicit is forbidden: not `current` / `zone` / `name` / `path` / `count`, but `current_zone_of_bridge` / `firewalld_zone` / `vm_name` / `staging_dir` / `mount_count`. The test: if reading the identifier in isolation (no surrounding code) raises "of what?" or "which one?", it is too vague - bake the answer into the name. Applies to all languages (bash, Python, Jinja, Ansible vars).
- The Claude Code execution environment is NOT the user's main development machine. Only read files within the current project directory (pwd). Do not explore paths outside it (e.g. do not `ls /home/user/` or read files from sibling directories).
- Use hyphens (-) not em-dashes (—).
- Documentation style (READMEs, role docstrings, human-facing comments): assume readers have dyslexia. Be as concise as possible, no fluff. Prefer tables and short bullets over prose. Cut anything that doesn't carry information. Applies to newly-written content from now on; existing docs are not retroactively rewritten unless they happen to be edited for other reasons.
- Ansible: use ansible-core only. Do not use community.general or other collections.
- Python scripts: all function signatures (parameters and return types) must carry type annotations. Prefer modern syntax (`list[str]`, `tuple[int, str]`, `X | None`) over the deprecated `typing` aliases (`List`, `Tuple`, `Optional`).
- Ansible task names: expose the underlying variable names directly (e.g. "Packages to install when `distro_packages_install_basic_tools` is true"). Ansible is already complex and obscure - task names should make the controlling variables immediately visible so debugging requires no reverse-engineering. Conventions inside task names:
  - Backtick (`` ` ``) identifiers and tokens that come from code, not prose: variable names (`setup_podman`), variable values when relevant (`libkrun`, `user`, `system`), commands/binaries (`zypper`, `rpm`, `podman`, `crun`), feature flags (`+LIBKRUN`), filenames (`containers.conf`), file paths (`~/.config/containers/containers.conf`, `/etc/containers/containers.conf`), and Jinja expansions like `` `{{ _podman_containers_conf_path }}` ``. Without backticks they blur into the surrounding English.
  - For tasks that write or remove a file, name the destination explicitly - either the literal path (when there's only one possibility per branch) or `` `{{ var }}` `` if the path is computed earlier. Reading the task name should answer "did this touch `~/...` or `/etc/...`?" without inspecting the module args.
- Target hosts are usually VMs (the playbook is mainly used to provision guest VMs, not bare-metal workstations). Consequence: features that themselves spin up a VM/microVM inside the guest - notably `podman_runtime: libkrun` - are off by default (`setup_podman: false`) because nested KVM in a guest is rarely wanted. Keep such VM-in-VM features opt-in; do not enable them globally without an explicit request.
- Never write the user's personal home layout - real directory names from their home, the actual username portion of paths, or any real paths learned from `local_vars/` and other gitignored personal-state files - into committed files (docstrings, comments, examples, READMEs, tests, anywhere). This repo is public; leaking real paths fingerprints the user and serves no one else (other users have different layouts). Use generic placeholders: `~/secrets`, `~/Personal/Projects/*`, `~/Personal/Vault/*` (the TitleCase pattern is clearly not anyone's real lowercase home layout; lowercase `~/projects/*` is too close to common real layouts). Knowledge of real paths learned from gitignored files stays inside the conversation; it does not leak into the repo. This rule applies to CLAUDE.md itself - do not quote the user's real paths even as examples of what to avoid.
- CLI arguments in code/scripts/Makefiles/subprocess calls: always use the long `--option` form (`--non-interactive`, `--yes`, `--recursive`), never the short flag form (`-n`, `-y`, `-r`). Short flags are opaque and command-specific (e.g. `zypper -n` = non-interactive, `tar -n` = no-recursion, `grep -n` = line-number); long flags are self-documenting in diffs and important for non-interactive sudo flags where misreading could change security-relevant behavior.
- Transparency before privileged actions: any script step that needs `sudo` / root password, or that modifies system files / fetches assets from outside the repo, must print BEFORE executing: (1) the exact command that will run (full argv, copyable as-is, e.g. via `shlex.join`), (2) the source of anything being installed (distro official repo vs `pip` / PyPI vs `curl | sh` vs vendor binary), (3) that sudo may prompt for a password. The user must be able to read what's about to happen and Ctrl+C with complete information; never hide privileged behavior behind a vague "Installing X...".
- Ansible role naming: role directories prefixed with `_` (e.g. `roles/_install_distro_packages/`) are internal utility roles - meant to be invoked via `ansible.builtin.include_role` from other roles, NOT as a standalone playbook entry point. They do not get a paired playbook in `playbooks/` and are not exposed via Makefile targets. The `_` prefix is the visible marker; the absence of `playbooks/<role_name>.yml` is the structural check. (Ansible has no official term for this - "sub-role" / "library role" are colloquial; for ansible they are just regular roles, the privacy is a project convention.) This extends the same `_` prefix convention used for internal task files (e.g. `roles/apparmor/tasks/_install.yml`).
- Ansible-managed user-home namespace - every face role MUST own exactly one hyphenated subdir under `~/.local/share/ansible-managed/`. Current mapping:

  ```
  ~/.local/share/ansible-managed/container-apps/       <- roles/container_apps
  ~/.local/share/ansible-managed/incus-agents/         <- roles/incus_agents
  ~/.local/share/ansible-managed/incus-vm/   <- roles/incus_vm
  ```

  - Subdir name uses hyphens; the Ansible role directory uses underscores. They differ on purpose (XDG-ish path vs Ansible role name conventions).
  - Everything the role deploys (manifest, zsh/bash completions, staging files, ssh keys, ...) lives inside its single subdir.
  - Uninstall is `rm -rf ~/.local/share/ansible-managed/<role-subdir>/`. No per-file chasing through a manifest.
  - Files MUST NOT land directly at `~/.local/share/ansible-managed/` itself. That breaks the `~/.local/share/ansible-managed/*/zsh-completions(N)` glob in `roles/zsh/templates/.zshrc.j2` and forces uninstall logic that can't just `rm -rf`.
  - Utility roles (e.g. `roles/container_templates`) may "guest" inside a face role's subdir, for example writing into `~/.local/share/ansible-managed/container-apps/container-templates/`. They MUST NOT own a separate `~/.local/share/ansible-managed/<x>/` of their own; they get cleaned up when their host face role is uninstalled.
