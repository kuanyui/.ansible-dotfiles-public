# roles/vm_incus TODO

Durable, role-local notes (same convention as the repo-root TODO.md).
Status: `[ ]` pending · `[~]` in progress · `[x]` done

## `ivm release-ram` - reclaim a running VM's host RAM without stopping it (NOT built)

Deferred on purpose: the user wants to confirm the real behavior on a host before we
build it. Recorded here so it is not re-derived.

**Why it is needed.** incus VMs have NO virtio-balloon **free-page-reporting** (verified
in incus source: `internal/server/instance/drivers/driver_qemu_templates.go` -
`qemuBalloon()` emits a plain `virtio-balloon-pci` with no `free-page-reporting`; QEMU
defaults that property off). So a running VM's host RSS is the **high-water-mark** of
pages the guest ever touched and is **NOT returned to the host until the VM stops**. The
only non-stop lever is the balloon.

**Mechanism to wrap (the balloon squeeze).**
- `incus config set <vm> limits.memory=<lower>` -> incus inflates the balloon
  (`driver_qemu.go:updateMemoryLimit`, via QMP `SetMemoryBalloonSizeBytes`, polling until
  the effective size shrinks within 1%) -> guest frees pages -> host reclaims.
- then restore `incus config set <vm> limits.memory=<original>`.

**Caveats (all verified / documented).**
- SLOW and may not hit the target in one pass; re-applying the lower value triggers
  another attempt (see incus issue #1904 - documents the timeout/desync).
- Hot **raise** back only works on incus **6.12+**; older incus needs a restart to grow.
- The balloon can only reclaim **free/reclaimable** guest memory - so it is far more
  effective now that the shipped templates leave `/tmp` on disk (reclaimable page cache)
  than with `sys.tmpfs /tmp` (used memory, stuck unless the guest has swap).
- Squeezing too low can OOM the guest.

**Open questions before building.**
- Pick the squeeze target (guest-used + headroom? a fixed fraction of `limits.memory`?).
- Auto-restore vs require the user to restore; gate hot-restore on incus >= 6.12.
- Confirm on a real host what lowering/restoring `limits.memory` actually does to the
  QEMU RSS (the env here has no incus).

**Until then.** `ivm stop` (then `ivm start`) is the reliable full reclaim. `ivm top`
gives a quick per-instance glance, but a VM's memory there is GUEST-reported and
under-reports the host RSS - use `ps -eo pid,rss,comm --sort=-rss | grep qemu` for the
true host cost.
