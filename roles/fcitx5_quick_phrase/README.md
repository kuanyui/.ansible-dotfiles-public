# fcitx5_quick_phrase role

Deploys fcitx5 Quick Phrase files (addon `quickphrase`; zh_TW UI name 快速片語)
to `~/.local/share/fcitx5/data/quickphrase.d/`.

Config-style face role (standard XDG data location, like `mpv`) - no
`~/.local/share/ansible-managed/` namespace dir.

No opt-in gate - run `make apply-fcitx5-quick-phrase` / `make check-fcitx5-quick-phrase`
(via `playbooks/fcitx5_quick_phrase.yml`).
No sudo.

## Deployed files

| File | Purpose |
| --- | --- |
| `quickphrase.d/llm.mb` | keyword `d` -> the standing LLM prompt preamble (user data; Chinese text on purpose) |

Uninstall: delete the files listed above from `~/.local/share/fcitx5/data/quickphrase.d/`,
then reload (command below).

## How Quick Phrase behaves (fcitx/fcitx5 `src/modules/quickphrase/`)

- Trigger key: `Super+grave` or `Super+semicolon` (default `TriggerKey` in
  `~/.config/fcitx5/conf/quickphrase.conf`; not managed here). The key handler does not
  check the active input method, so it works under keyboard-us / mozc / chewing alike.
- Type a keyword, pick the candidate. Matching is by PREFIX: `d` lists every keyword
  that starts with `d`.
- Every `*.mb` in `quickphrase.d/` plus `data/QuickPhrase.mb` is merged into ONE table
  (`std::multimap`). A keyword present in two files shows both candidates, earlier-loaded
  first. A `<name>.mb.disable` file next to `<name>.mb` disables that file.
- Line format: `keyword<whitespace>phrase`. Wrap the phrase in `"..."` to use the
  escapes `\n` `\t` `\\` `\"` (multi-line phrases). A bare `"` inside a quoted phrase
  rejects the whole line.

## Reload

fcitx5 reads `quickphrase.d/` at start and on an addon config reload. `fcitx5-remote -r`
is NOT enough: `Instance::reloadConfig` reloads only the global config, never an addon's
data files. The role therefore calls the per-addon D-Bus method when a file changed and
fcitx5 is running (`fcitx5-remote --check` exit 0):

```
busctl --user call org.fcitx.Fcitx5 /controller org.fcitx.Fcitx.Controller1 ReloadAddonConfig s quickphrase
```

fcitx5 not running (ssh / tty / not logged in): the play prints a note; the files are
read at the next fcitx5 start.

## Adding a phrase file

1. Add `roles/fcitx5_quick_phrase/files/quickphrase.d/<name>.mb`.
2. Add `<name>.mb` to the `loop` in `tasks/main.yml`.
3. `make apply-fcitx5-quick-phrase`.

## Out of scope

Quick Phrase files only. The chewing keys + keyboard-us / mozc / chewing profile setup
(`roles/vm_incus/files/setup-fcitx5-input.sh`) still runs by hand on the host - a general
`roles/fcitx5` for it is deferred, see `TODO.md`, "fcitx5 host-side wiring".
