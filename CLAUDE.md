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

- All code content (comments, variable names, strings) must be in English.
- The Claude Code execution environment is NOT the user's main development machine. Only read files within the current project directory (pwd). Do not explore paths outside it (e.g. do not `ls /home/user/` or read files from sibling directories).
- Use hyphens (-) not em-dashes (—).
- Ansible: use ansible-core only. Do not use community.general or other collections.
- Ansible task names: expose the underlying variable names directly (e.g. "Packages to install when `packages_install_basic_tools` is true"). Ansible is already complex and obscure - task names should make the controlling variables immediately visible so debugging requires no reverse-engineering. Conventions inside task names:
  - Backtick (`` ` ``) identifiers and tokens that come from code, not prose: variable names (`setup_podman`), variable values when relevant (`libkrun`, `user`, `system`), commands/binaries (`zypper`, `rpm`, `podman`, `crun`), feature flags (`+LIBKRUN`), filenames (`containers.conf`), file paths (`~/.config/containers/containers.conf`, `/etc/containers/containers.conf`), and Jinja expansions like `` `{{ _podman_containers_conf_path }}` ``. Without backticks they blur into the surrounding English.
  - For tasks that write or remove a file, name the destination explicitly - either the literal path (when there's only one possibility per branch) or `` `{{ var }}` `` if the path is computed earlier. Reading the task name should answer "did this touch `~/...` or `/etc/...`?" without inspecting the module args.
- Target hosts are usually VMs (the playbook is mainly used to provision guest VMs, not bare-metal workstations). Consequence: features that themselves spin up a VM/microVM inside the guest - notably `podman_runtime: libkrun` - are off by default (`setup_podman: false`) because nested KVM in a guest is rarely wanted. Keep such VM-in-VM features opt-in; do not enable them globally without an explicit request.
