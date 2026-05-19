# roles/apparmor

Deploys and enforces AppArmor profiles for managed applications.

## Profile naming

All profiles deployed to `/etc/apparmor.d/` follow these rules (filename and profile name inside
the file must match):

- `local_` prefix: all locally managed profiles (e.g. `local_foo`)
- `local_attachmentless_` prefix: profiles with no executable attachment; must be invoked
  explicitly via `aa-exec` or an explicit `Px ->` transition rule (e.g. `local_attachmentless_glycin`)

File extensions:
- Static profiles under `files/profiles/`: `.aa` suffix (e.g. `local_attachmentless_glycin.aa`)
- Jinja2 templates under `templates/`: `.aa.j2` suffix (e.g. `local_attachmentless_firefox.aa.j2`)
- Deployed to `/etc/apparmor.d/`: no extension

## Glycin image loader sandbox (local_attachmentless_glycin)

Firefox uses Glycin for image loading. Glycin dispatches image decoding through bwrap to isolate
decoders inside a mount namespace. The calling profile transitions bwrap to glycin's own profile
(non-stacked):

```
/usr/bin/bwrap Px -> local_attachmentless_glycin,
```

### Why non-stacked (not intersection)

AppArmor profile stacking (`Px -> app//&glycin`) enforces the intersection of both profiles.
This sounds like a security win but creates a maintenance trap: every rule in glycin
(`capability setpcap`, `capability net_admin`, `mount`, `umount`, `pivot_root`, ...) must also
appear in the calling profile or it is silently denied. The calling profile ends up granting
capabilities it does not actually use.

The actual isolation boundary is bwrap's mount namespace: bwrap only bind-mounts what the decoder
needs (image data or a socket) into the sandbox. The decoder cannot reach the calling app's data
regardless of what the glycin profile allows, because bwrap never mounted it there. AppArmor
on the glycin side enforces capability and syscall constraints; the namespace handles file
visibility. Stacking adds no meaningful security benefit in this architecture.
