# trusted_pubkeys

Pin well-known **public** keys for the current user. User-level only - no
system-wide trust, no `sudo`.

Gate: `setup_trusted_pubkeys` (default `false`, in `group_vars/all.yml`).

## What it does

| part | source | written to |
| --- | --- | --- |
| GitHub + GitLab SSH host keys | pinned in `vars/main.yml` | `~/.ssh/known_hosts` |
| Debian CD signing GPG keys | pinned armored in `files/` | dedicated keyring `~/.gnupg/ansible-trusted-debian-cd.gpg` |
| openSUSE Project Signing Key | pinned armored in `files/` | dedicated keyring `~/.gnupg/ansible-trusted-opensuse.gpg` |

So `git clone git@github.com:...` / `git@gitlab.com:...` over SSH no longer shows
the `authenticity of host ... can't be established` TOFU prompt, and you can verify
downloaded Debian / openSUSE images offline.

## Verifying Debian images

The 3 Debian CD signing keys go into a **dedicated** keyring (not your main
`~/.gnupg` pubring) - the file itself is the ansible-managed boundary, so
uninstall is just `rm` of it. Verify a downloaded image:

```
gpg --no-default-keyring --keyring ~/.gnupg/ansible-trusted-debian-cd.gpg \
    --verify SHA256SUMS.sign SHA256SUMS
```

Handy alias:

```
alias verify-debian-iso='gpg --no-default-keyring --keyring ~/.gnupg/ansible-trusted-debian-cd.gpg --verify'
```

Needs `gpg`; if it is absent the role prints a warning and skips this part (the
SSH part is unaffected). On apply, the role asserts each imported key's
fingerprint matches the pinned value in `vars/main.yml`, failing loudly otherwise.

## Verifying openSUSE (Tumbleweed) images

Same scheme, own keyring. openSUSE signs the `.sha256` of each image with the
**openSUSE Project Signing Key** and ships the detached sig as `.sha256.asc`:

```
gpg --no-default-keyring --keyring ~/.gnupg/ansible-trusted-opensuse.gpg \
    --verify <img>.qcow2.sha256.asc <img>.qcow2.sha256
```

(then check the `.sha256` matches the image's actual sha256sum). This is the key
`qvm` can use to GPG-verify its Tumbleweed Cloud qcow2 download.

## Why pinned (hardcoded), not fetched

- Public host keys - committing them leaks nothing.
- Pinning = integrity: reviewed once, frozen; any change shows in `git diff`.
- Fetching at apply time would trust the network every run and could silently
  accept a swapped key (MITM of a future `git clone`).

## Updating when a forge rotates its key

Rare - GitHub rotated its RSA host key once (2023-03-24); ECDSA/Ed25519 never. A
rotation surfaces as ssh's loud `REMOTE HOST IDENTIFICATION HAS CHANGED`; that is
the signal to update the pin as a deliberate, reviewed change.

Re-verify, then edit `vars/main.yml`:

```
ssh-keyscan -t rsa,ecdsa,ed25519 github.com gitlab.com | ssh-keygen -lf -
```

Compare the fingerprints against the published values:

- GitHub: <https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints>
- GitLab: <https://docs.gitlab.com/user/gitlab_com/> (SSH host keys)

Debian CD keys roll per stable release and are additive (old keys still verify
old images). To add one: re-verify against <https://www.debian.org/CD/verify>,
drop the armored key into `files/`, and add it to `trusted_pubkeys_debian_cd_keys`
in `vars/main.yml`.

The openSUSE Project Signing Key rotates rarely. The authoritative armored copy
is the repo signing key at
<https://download.opensuse.org/tumbleweed/repo/oss/repodata/repomd.xml.key>;
re-verify it produces a GOOD signature over a live image's `.sha256.asc`, then
update the armored file + fingerprint in `trusted_pubkeys_opensuse_keys`.

## Layout note

Not in the `~/.local/share/ansible-managed/` namespace: this role writes
standard locations (`~/.ssh/known_hosts` and a dedicated keyring under
`~/.gnupg/`), the same way `roles/zsh` writes `~/.zshrc`.
