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

- **Execution transparency is a core principle.** When a behavior can be visible or hidden, choose visible: fail loudly (never swallow an error to keep a step green), print commands before running them, never hide a step behind a vague message. A silent wrong "success" is worse than a loud failure - the concrete forms are the print-command and privileged-action rules below.
- NEVER commit, stage, or push (`git commit` / `git add` / `git push`) - and don't offer to, even after large multi-file changes. Make the edits and stop; the user reviews and commits in their own batches, so leave the working tree dirty.
- Task tracking: the in-session task tool (TaskCreate / TaskList) is local, ephemeral, and not git-tracked, so it doesn't survive across machines. Mirror every task into a committed `TODO.md` (one line each: status + subject) - the durable, in-repo source of truth; keep the two in sync.
- Auto-memory (`~/.claude/projects/<project>/memory/`) is local-only and doesn't follow the user across machines - never rely on it. Anything durable (a project rule, working preference, debug lesson) goes in THIS git-tracked `CLAUDE.md`, not auto-memory. Tempted to `Write` a memory file? Add a `CLAUDE.md` bullet instead.
- Debugging any external tool (`incus` / `podman`, a library, daemon, API, framework): `WebFetch` / `WebSearch` its upstream source / docs / issues FIRST, then conclude. Cite the source (GitHub raw path, doc URL, dated thread), or frame the claim as an explicit assumption to verify - never fabricate "version N does B" from memory. "I remembered" is not a citation.
- All code content (comments, variable names, strings) must be in English.
- Variable names must be unambiguous in isolation - the name alone answers "X of what?". Not `current` / `zone` / `name` / `path` / `count`, but `current_zone_of_bridge` / `firewalld_zone` / `vm_name` / `staging_dir` / `mount_count`. Applies to all languages (bash, Python, Jinja, Ansible).
  - Second test, just as binding: when the value comes from a known system/convention (ansible fact, env var, API field, distro concept), name it with that source's EXACT identifier so the value domain is inferable. Not `os_family` but `ansible_os_family` (values `Debian` / `Suse` / `RedHat`, not `opensuse`); not `family` / `distro` / `mgr` but `ansible_os_family` / `os_distro` / `package_manager`. Constants/maps too: `DISTRO_TO_ANSIBLE_OS_FAMILY`, not `DISTRO_TO_FAMILY`.
- The Claude Code execution environment is NOT the user's main machine. Read only within the project dir (pwd); don't explore outside it (no `ls /home/user/`, no sibling dirs).
- Use hyphens (-) not em-dashes (—).
- Documentation (READMEs, role docstrings, human-facing comments): assume dyslexic readers. Concise, no fluff; tables and short bullets over prose; cut anything that carries no information. Applies to newly-written content; don't retroactively rewrite existing docs unless editing them anyway.
- "Print the command, then execute": when pointing the user at a next command (Claude replies, Makefile recipes, script error helpers), first echo the exact bare starter on its own plain-text line - that's what they copy-paste (inline execution leaves the string nowhere). Bare invocation only (`python3 scripts/foo.py`, not `... --help`) so they can append args; no placeholder garbage like `<path> [...]` (breaks double-click). Script "next-command" helpers: `echo "Run:"`, blank line, the bare command, blank line, a divider, blank line, then exec the script with `--help` so its full usage prints as reference.
- Ansible: use ansible-core only, no community.general or other collections.
- Python: every function signature needs type annotations (params + return). Modern syntax (`list[str]`, `tuple[int, str]`, `X | None`), not the deprecated `typing` aliases (`List`, `Tuple`, `Optional`).
- Ansible task names: name the controlling variables directly (e.g. "Packages to install when `provision_distro_packages_install_basic_tools` is true") so debugging needs no reverse-engineering. Conventions:
  - Backtick anything from code, not prose: var names (`setup_podman_oci_runtimes`), values (`libkrun`, `user`, `system`), binaries (`zypper`, `podman`, `crun`), flags (`+LIBKRUN`), filenames/paths (`containers.conf`, `~/.config/containers/containers.conf`, `/etc/containers/containers.conf`), Jinja (`` `{{ _podman_containers_conf_path }}` ``). Otherwise they blur into the English.
  - Tasks that write/remove a file: name the destination (the literal path, or `` `{{ var }}` `` if computed earlier) so the name answers "`~/...` or `/etc/...`?" without reading the module args.
- Target hosts are usually VMs, not bare metal. So VM-in-VM features (notably `podman_runtime: libkrun`) stay off by default (`setup_podman_oci_runtimes: false`) - nested KVM in a guest is rarely wanted. Keep them opt-in; don't enable globally without an explicit request.
- Never write the user's real home layout into committed files (docstrings, comments, examples, READMEs, tests - anywhere, incl. this CLAUDE.md): real dir names, the real username in paths, or any path learned from `local_vars/` and other gitignored state. This repo is public - leaking paths fingerprints the user and helps no one (others have different layouts). Use generic placeholders: `~/secrets`, `~/Personal/Projects/*`, `~/Personal/Vault/*` (TitleCase, clearly not a real lowercase home; avoid `~/projects/*`, too close to real layouts).
- CLI args in code / scripts / Makefiles / subprocess calls: always the long `--option` form (`--non-interactive`, `--yes`, `--recursive`), never short (`-n`, `-y`, `-r`). Short flags are opaque and command-specific (`-n` = non-interactive in `zypper`, no-recursion in `tar`, line-number in `grep`); long flags self-document in diffs and matter for security-relevant sudo flags.
- Transparency before privileged actions: any step that needs `sudo` / root, modifies system files, or fetches outside-repo assets must print BEFORE running: (1) the exact command (full argv, copyable, e.g. via `shlex.join`), (2) the source of anything installed (distro repo vs `pip` / PyPI vs `curl | sh` vs vendor binary), (3) that sudo may prompt. Never hide privileged behavior behind a vague "Installing X...".
- Ansible role naming: `_`-prefixed role dirs (e.g. `roles/_install_distro_packages/`) are internal utility roles - invoked via `ansible.builtin.include_role` from other roles, never as a standalone playbook entry point. No paired `playbooks/<role>.yml`, no Makefile target. The `_` prefix is the marker; the missing playbook is the structural check. (Same `_` convention as internal task files like `roles/apparmor/tasks/_install.yml`.)
- Ansible-managed home namespace: every face role owns exactly one hyphenated subdir under `~/.local/share/ansible-managed/`:

  ```
  ~/.local/share/ansible-managed/container-apps/       <- roles/container_apps
  ~/.local/share/ansible-managed/vm-incus/             <- roles/vm_incus
  ```

  - Subdir uses hyphens, the role dir uses underscores - on purpose (XDG-ish path vs Ansible role-name convention).
  - Everything the role deploys (manifest, completions, staging files, ssh keys, ...) lives inside that one subdir.
  - Uninstall = `rm -rf ~/.local/share/ansible-managed/<role-subdir>/`. No per-file manifest chasing.
  - Nothing lands directly at `~/.local/share/ansible-managed/` itself - it breaks the `.../*/zsh-completions(N)` glob in `roles/zsh/templates/.zshrc.j2` and defeats `rm -rf` uninstall.
  - Utility roles (e.g. `roles/container_templates`) may guest inside a face role's subdir (e.g. `.../container-apps/container-templates/`); they must NOT own a top-level subdir of their own - they're cleaned up with their host face role.
