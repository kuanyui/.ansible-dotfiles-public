# TODO: VM audio for `ivm` - investigation notes

Whether/how to give an `ivm` VM working audio. Recorded as a STANDALONE note because it
spans FOUR layers (incus project permission / host `raw.qemu` / guest provision / SPICE
client playback) and the permission cost is project-wide - "affects too much" to just
bolt on. Nothing implemented yet; this is the design record + open questions.

Status: `[ ]` pending  `[~]` in progress  `[x]` done

## Current stance: deliberately NOT supported

`docs/survey-of-quickemu.md` is explicit: **"Audio: not a goal"**, and "No 3D / USB /
audio; SPICE console is software-rendered. Not a desktop-replacement tool." `ivm` = a
headless dev VM; audio (full-duplex) is quickemu/`qvm`'s territory. So adding this is a
deliberate scope-expansion, not a bug-fix - hence the "is it worth it" framing below.

## It IS technically possible (unlike GPU virgl)

Audio differs from the virgl-3D dead-end: incus's bundled QEMU is built WITHOUT virgl, so
`raw.qemu` can't add 3D (see `docs/incus-hardware-capabilities.md`). An audio DEVICE, on
the other hand, CAN be added via `raw.qemu`:

    incus config set <vm> raw.qemu -- "-device intel-hda -device hda-duplex -audio spice"

- QEMU 8.1+ (incus's current bundle) needs `-audio spice`. Older QEMU used the split form
  `-audiodev spice,id=snd0 -device intel-hda -device hda-duplex,audiodev=snd0`.
- Heard through `ivm gui` = `incus console --type=vga` (the SPICE console) - the path
  `ivm` ALREADY has. No extra mechanism on the ivm side.
- Source: simos (incus/LXD core dev), "How to run a Windows VM on Incus on Linux":
  https://blog.simos.info/how-to-run-a-windows-virtual-machine-on-incus-on-linux/

## How the audio actually plays: CLIENT-side (this answers "host loses sound for how long?")

`-audio spice` means QEMU ships guest audio over the SPICE protocol; the **SPICE CLIENT**
(the `ivm gui` / remote-viewer window) plays it - NOT the VM, NOT the host QEMU process.
(All the troubleshooting threads found are about remote-viewer/virt-viewer playback,
which confirms the client-side model.)

Therefore the "host loses audio" scare is bounded:
- What grabs host audio is the **viewer app** (playing VM sound on the host), not the VM.
  **Closing the `ivm gui` window -> host audio returns immediately**; the VM keeps running
  headless (nobody is receiving its SPICE audio). NOT "until the VM is shut down".
- VM running but no `ivm gui` open -> host unaffected (no client is playing).
- simos's one-liner "I lose audio from the host" (no mechanism, no fix given) is most
  likely a VERSION bug, not by-design: QEMU 9.1.1 once broke virt-viewer SPICE audio
  (https://bbs.archlinux.org/viewtopic.php?id=300475); virt-viewer 8.0 had an audio bug
  (https://github.com/quickemu-project/quickemu/issues/209). On a modern PipeWire host the
  viewer usually SHARES the sink, so host audio is unaffected. Must verify on the real host.

## The three gotchas

1. **[project-wide] restricted lowlevel** - `ivm` runs under the unprivileged incus
   group's `user-<uid>` restricted project. `restricted.virtual-machines.lowlevel`
   defaults to `block`, which blocks `raw.qemu` entirely. Enabling it -
       sudo incus project set user-$(id -u) restricted.virtual-machines.lowlevel=allow
   - is **project-wide**: EVERY VM in that project can then use ANY `raw.qemu` (not just
   audio; raw.qemu passes arbitrary QEMU args). Widens the sandbox significantly. incus has
   NO per-vm lowlevel toggle and NO native audio device type, so this is the ONLY path.
   Same shape as the `expose` proxy-device gotcha (`restricted.devices.proxy=allow`).
   Source: incus project docs
   https://linuxcontainers.org/incus/docs/main/reference/projects/
   NOTE: incus host must be >= 6.0.6 / 6.21.0 (CVE-2026-23953: lowlevel-restriction bypass
   via instance snapshot).
2. **host audio conflict** - client-side (see above); scoped to while the viewer is open;
   close `ivm gui` to restore. Frequently absent on a PipeWire host.
3. **guest audio stack** - the guest needs PipeWire/PulseAudio + ALSA so guest apps reach
   the intel-hda device. `desktop_lxqt` likely already ships it (LXQt DEs usually do) -
   VERIFY before deciding whether a separate feature is needed.

## Design questions (open)

- **No true "instant toggle" subcommand is clean.** `raw.qemu` is a START-time arg, so
  changing it needs a VM reboot (not instant). And project lowlevel needs `sudo` (against
  ivm's no-sudo, incus-socket-only design). A live on/off switch fights both facts.
- **Recommended model instead:** configure the audio device ONCE (at create/provision),
  leave it. Day-to-day "audio on/off" = whether you open `ivm gui` (only a connected
  client plays) + guest volume. No reboot, no subcommand needed.
- **Contain the permission risk by ISOLATION, not by toggling:** put desktop/audio VMs in
  a SEPARATE incus project with `lowlevel=allow`, keep the main dev project `block`. The
  raw.qemu blast radius stays in that one project. (vs opening lowlevel on the main
  project, which the user flagged as "too much".)
- **If `ivm` helps at all:** `ivm audio <vm>` = a one-shot SETUP (set raw.qemu; detect the
  project isn't allowed and print the exact sudo line; reboot) - NOT a live toggle.
- **guest/host split** (mirrors the gui split): guest audio stack -> a provision feature
  (sibling of `gui_x11` / `desktop_lxqt`); host `raw.qemu` + permission -> the ivm side
  (instance config / optional `ivm audio`). Cf. `gui_x11` (provision installs the X
  server) vs `ivm gui` (opens the SPICE console).

## Why this "affects too much" (the layers touched)

- incus PROJECT permission (admin, project-wide, a security tradeoff)
- ivm (instance config / possible `ivm audio` subcommand / possible schema field `hw.audio`)
- provision (a guest audio-stack feature, OR confirm `desktop_lxqt` already covers it)
- SPICE client (`ivm gui` host-side playback + the host-audio conflict)

Three tiers - host-config / guest-provision / client-playback - is exactly why this is a
note first, not a bolt-on.

## TODO (when/if picked up)

- [ ] Verify `desktop_lxqt` already ships PipeWire/PulseAudio + ALSA (if yes, no separate
  `audio_guest` provision feature is needed for the desktop case)
- [ ] Decide: separate `lowlevel=allow` project (isolation) vs opening lowlevel on the
  main dev project
- [ ] Decide: an `ivm audio <vm>` one-shot setup subcommand, vs just documenting the manual
  `raw.qemu` steps
- [ ] Real-host test: `raw.qemu` audio + `ivm gui` actually plays guest sound; measure the
  host-audio conflict on THIS host's PipeWire (does host keep sound while the viewer plays?
  does closing the viewer restore it?)
- [ ] Confirm the incus host is >= 6.0.6 / 6.21.0 (CVE-2026-23953)
- [ ] If implemented: a gui-gated schema field (e.g. `hw.audio: true`) that emits the
  raw.qemu line + the project-permission hint (die loudly with the sudo command if the
  project blocks lowlevel, same spirit as `expose`'s proxy-device rollback)
