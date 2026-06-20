# firefox_tunes

Apply `about:config` tweaks to **every** Firefox profile of the current user, to
cut SSD writes. User-level only, no `sudo`. Native Firefox (`~/.mozilla/firefox/`).

No opt-in gate - run `make apply-firefox-tunes` (its dedicated target). Not wired
into `playbooks/user.yml`.

## How

Writes a `user.js` into each profile (enumerated from `profiles.ini`). Firefox
reads `user.js` at **every** startup and applies it, so the prefs are permanent
and an in-session about:config edit reverts on the next launch. Do NOT edit
`prefs.js` (Firefox overwrites it). Restart Firefox for changes to take effect.

## What it sets

| pref | value | why |
| --- | --- | --- |
| `browser.sessionstore.interval` | 30 min (Firefox default 15 s) | the dominant idle SSD write (`recovery.jsonlz4`); a clean shutdown still saves immediately, so this only affects post-crash recovery |
| cache prefs | per strategy below | keep the cache off the SSD |

### Cache strategy (`firefox_tunes_cache_strategy`)

| value | prefs | cache survives a Firefox restart? |
| --- | --- | --- |
| `ram` (default) | `browser.cache.disk.enable=false` + memory cache | no (RAM only) |
| `tmpfs_disk` | disk cache redirected to a tmpfs dir under `/tmp` | yes, until reboot |

`tmpfs_disk` also drops a `~/.config/user-tmpfiles.d/firefox-tunes-cache.conf`
entry so the tmpfs dir is recreated each boot - Firefox does NOT create the
`browser.cache.disk.parent_directory` itself.

## Tunables (`defaults/main.yml`)

`firefox_tunes_sessionstore_interval_ms`, `firefox_tunes_memory_cache_capacity_kib`,
`firefox_tunes_disk_cache_capacity_kib`, `firefox_tunes_disk_cache_tmpfs_dir`.

## Layout note

Not in the `~/.local/share/ansible-managed/` namespace: it writes standard profile
dotfiles (`~/.mozilla/firefox/<profile>/user.js`), the same way `roles/zsh` writes
`~/.zshrc`.
