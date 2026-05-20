# TODO

## Extract `local_mixin_gpu_probe` abstraction (deferred)

Two profiles currently inline the same "allow userspace GPU/render API metadata
probing without granting hardware access" pattern:

- `templates/mpv/local_base_mpv.aa.j2` - `/dev/dri/`, `/usr/share/vulkan/{icd.d,implicit_layer.d}/`, `/usr/share/glvnd/egl_vendor.d/`
- `templates/telegram/local_pathbased_telegram.aa.j2` - `/usr/share/glvnd/egl_vendor.d/` (Qt EGL probe)

`files/profiles/local_mixin_gpu.aa` also contains the same 4 paths.

When a third caller (some Qt/GTK app intentionally denied GPU hardware but still
probing render APIs at startup) hits the same audit-log spam, extract a new
abstraction:

- `files/profiles/local_mixin_gpu_probe.aa` - the 4 read-only paths above.
- Refactor `local_mixin_gpu` to `#include` the new probe mixin, so the layering
  becomes `gpu_probe` (metadata only) `subset of` `gpu` (metadata + hardware nodes).
- Replace the inline rules in mpv base and telegram pathbased with the include.

Why deferred (2026-05-21): only 2 callsites, and their path sets are not
identical (telegram only needs glvnd; mpv also needs vulkan + `/dev/dri/`).
Premature extraction would either over-grant inert config reads to telegram or
require a more granular split. The break-even point is the 3rd caller, when
the minimal shared set and naming will be more obvious.

Security invariant to preserve when extracting: the new mixin must NEVER include
`/dev/dri/renderD*` or `/dev/nvidiactl`. Those device nodes are the actual GPU
boundary and must stay exclusively in `local_mixin_gpu`.
