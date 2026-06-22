# Seccomp layer for Telegram (design notes - NOT yet implemented)

Why: AppArmor mediates LSM hooks (file / cap / network-family / mount / ptrace /
signal / userns / io_uring / mqueue), but it does **not** filter syscalls. The
kernel-exploit primitives below have no AppArmor rule keyword, so only seccomp (or a
sysctl) can block them. The dropped bwrap wrapper never had `--seccomp` either, so this
gap is pre-existing, not a bwrap regression.

AppArmor-blind LPE primitives we want gone:

| Primitive | AppArmor? | Seccomp / sysctl |
|---|---|---|
| `userfaultfd` | no | seccomp, or `vm.unprivileged_userfaultfd=0` |
| `perf_event_open` | no | seccomp, or `kernel.perf_event_paranoid>=2` |
| `keyctl` / `add_key` / `request_key` | no (deny_keyrings only blocks file paths) | seccomp |
| `io_uring` setup | yes (`audit deny io_uring`) | seccomp = defense-in-depth |
| SysV shm/sem | no (`mqueue` deny covers msg queues only) | seccomp |

## Verified facts (checked upstream, do not re-derive from memory)

1. **`systemd-run --scope` cannot apply seccomp.** `SystemCallFilter` /
   `RestrictAddressFamilies` are exec-sandboxing, **service-unit only**. A scope's
   process is forked by `systemd-run` itself, bypassing the manager exec path, so these
   properties are ignored (or rejected). => must use a transient **service** (default
   `systemd-run` mode, no `--scope`).
2. **A transient `--user` service does NOT inherit the caller env.** It runs detached
   with the service manager as parent. GUI vars must be forwarded explicitly with
   `-E VAR` (no `=value` => imports the caller's current value).
3. `--pipe --wait` => runs synchronously, stdio passes through. Bonus: makes the wrapper
   behave like a normal command from a terminal (the reason a wrapper beats inlining in
   `.desktop`: one command, same seccomp from terminal AND `.desktop`).
4. Repeated `-p SystemCallFilter=` merge-vs-override is **undocumented** -> avoided by
   using a single assignment (see denylist choice below).

## Decision: wrapper script, not inline `.desktop`

`.desktop` `Exec=` is not shell-parsed (Desktop Entry Spec): single quotes are literal,
multi-token values need spec quoting, launchers (KDE KService / gio / gtk-launch) differ
-> fragile, and it can't echo the command or be run from a terminal. A `~/.local/bin/`
wrapper fixes all of it and is one file. `.desktop` becomes `Exec=<wrapper> %u`.

Wrapper name: must NOT be `Telegram` (shadows `/usr/bin/Telegram`, = old bwrap wrapper
name) nor `telegram-desktop` (in the idempotence removal list). Candidate: `telegram`
(lowercase) / `tg` / `telegram-seccomp`. **OPEN.**

## Proposed wrapper

```bash
#!/bin/bash
# MANAGED BY ANSIBLE - DO NOT EDIT MANUALLY (src: roles/apparmor/templates/telegram/<this>.j2)
set -euo pipefail

# Transient --user service does NOT inherit caller env; forward GUI vars (skip unset ones).
ENV_FWD=()
for v in WAYLAND_DISPLAY DISPLAY XAUTHORITY XDG_RUNTIME_DIR \
         DBUS_SESSION_BUS_ADDRESS XDG_CURRENT_DESKTOP XDG_SESSION_TYPE; do
  [ -n "${!v:-}" ] && ENV_FWD+=(-E "$v")
done

CMD=(systemd-run --user --pipe --wait --collect "${ENV_FWD[@]}"
  -p SystemCallArchitectures=native          # close 32-bit/x32 ABI seccomp bypass
  -p SystemCallErrorNumber=EPERM             # denied syscall -> EPERM, not SIGSYS kill (fail-soft)
  -p 'SystemCallFilter=~userfaultfd perf_event_open keyctl add_key request_key @io_uring @obsolete @cpu-emulation @raw-io @swap @reboot @module @debug'
  /usr/bin/env --unset=LD_LIBRARY_PATH --unset=PYTHONPATH LIBGL_ALWAYS_SOFTWARE=1
  /usr/bin/Telegram)

printf 'launching under seccomp: %q ' "${CMD[@]}"; echo
exec "${CMD[@]}" "$@"
```

## Denylist vs allowlist (deliberate)

- **Denylist** (`~...`) chosen because the workflow is enforce-only, no `SystemCallLog=`
  validation pass. It kills exactly the AppArmor-blind primitives above; Telegram never
  uses them, so near-zero breakage risk.
- Scope of value: this is "patch AppArmor's syscall blind spot", **not** a full sandbox.
  Syscalls Telegram legitimately needs (`setsockopt` / `futex` / `ioctl`) stay open - an
  `@system-service` allowlist would not block those either.
- Upgrade path (stronger, later): base on `@system-service` allowlist, run once with
  `-p SystemCallLog=...` (mirrors aa-complain), collect from `journalctl --user`, tighten,
  then enforce. Needs the merge-semantics check from fact 4.

## Optional system-wide sysctl hardening (not Telegram-specific)

`vm.unprivileged_userfaultfd=0`, `kernel.perf_event_paranoid>=2`,
`kernel.unprivileged_bpf_disabled=1`, `kernel.yama.ptrace_scope>=1`.

## Open / not done

- [ ] Wrapper name.
- [ ] Implement: template + deploy task (`0755`, managed header), rewire `.desktop`
      `Exec=`, reuse idempotence removal block, run `make apparmor-sandbox`.
- [ ] Decide allowlist upgrade (later) vs keep denylist.

## Sources

- https://wiki.archlinux.org/title/Systemd/Sandboxing
- https://wiki.debian.org/ServiceSandboxing
- https://man.archlinux.org/man/systemd-run.1.en


# a
 那個 systemd-run 直接放在 telegram 那個 desktop 足夠嗎？還是最好要搞個 sh?

● 短答:能塞進 .desktop,但我建議用一個薄 wrapper .sh。 不是因為 systemd-run 本身複雜,是因為 .desktop 的 Exec= 有幾個硬限制會讓那串 inline
  參數變脆。

  為什麼 .desktop 直塞會脆

  .desktop 的 Exec= 不是用 shell 解析的(freedesktop Desktop Entry Spec 明寫 must not be passed to a shell),它用自己的 tokenizer:

  ┌───────────────────────────────┬────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │             問題              │                                                    後果                                                    │
  ├───────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ 單引號 '...' 是字面字元,不是  │ -p SystemCallFilter='@system-service' 會把 '@system-service'(含引號)整串丟給 systemd-run → 解析失敗        │
  │ quoting                       │                                                                                                            │
  ├───────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  .desktop 的 Exec= 不是用 shell 解析的(freedesktop Desktop Entry Spec 明寫 must not be passed to a shell),它用自己的 tokenizer:

  ┌──────────────────────────────────────┬────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │                 問題                 │                                                                    後果                                                                    │
  ├──────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ 單引號 '...' 是字面字元,不是 quoting │ -p SystemCallFilter='@system-service' 會把 '@system-service'(含引號)整串丟給 systemd-run → 解析失敗                                        │
  ├──────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ 只有 " 是 quote,且 ` $ \ 要 escape   │ 多 token 的值(~@obsolete @cpu-emulation ...、RestrictAddressFamilies='AF_UNIX AF_INET ...')得改用 .desktop 的雙引號規則,可讀性歸零         │
  ├──────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ 各 launcher 解析不完全一致           │ KDE 的 KService parser / gio launch / gtk-launch / dbus-activation 行為有差;最慘的是只在 tg:// link 啟動(%u 帶值)時才爆,日常點圖示看不出來 │
  ├──────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Exec= 無法 echo / 分支               │ 違反你 repo 的「print the privileged command then execute」;而且做不了下面兩件你一定需要的事                                               │
  └──────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

  後兩件是關鍵,不是潔癖:

  - 驗證需要 SystemCallLog ↔ SystemCallFilter 切換 — Telegram 是大型 Qt app,allowlist 必須先用 log-only 跑一輪收集再 enforce。script 裡一個變數搞定,.desktop 裡得維護兩份 Exec。
  - fallback 要「大聲」 — 沒有 user systemd manager / 沒 systemd-run 時(某些登入環境),要 fall back 成直接 exec 並對 stderr 大聲警告「seccomp 層沒生效,只剩 AppArmor」(符合你「fail loudly,別把降級藏起來」)。.desktop 一行做不到分支。

  ▎ 有個 trick 能讓 .desktop 直塞勉強可行:把每個 deny group 拆成獨立 -p(-p SystemCallFilter=~@obsolete -p SystemCallFilter=~userfaultfd ...),讓每個值都不含空白 → 就不必 quoting。但它還是拿不到上面那兩個(validation toggle、loud
  ▎ fallback)+ transparency echo,所以省一個檔案不值得。

  建議形狀(wrapper 約 12 行,不是把 bwrap 加回來)

  跟你 CLAUDE.md 既有的「~/.local/bin/ managed wrapper」慣例完全一致 —沒有 namespace、沒有 userns,只有 seccomp + 一個 echo + 一個 fallback:

  #!/bin/bash
  # =============================================================================
  # MANAGED BY ANSIBLE - DO NOT EDIT MANUALLY
  #   src: roles/apparmor/templates/telegram/<this>.j2
  # =============================================================================
  set -euo pipefail
  MODE="${TELEGRAM_SECCOMP_MODE:-enforce}"   # enforce | log  (log = 收集 syscall 的驗證輪)

  ARGS=(systemd-run --user --scope --collect
    -p SystemCallArchitectures=native
    -p RestrictAddressFamilies="AF_UNIX AF_INET AF_INET6 AF_NETLINK"
    -p "SystemCall${MODE/enforce/Filter}${MODE/log/Log}=@system-service"
    -p SystemCallFilter=~@obsolete -p SystemCallFilter=~@cpu-emulation
    -p SystemCallFilter=~userfaultfd -p SystemCallFilter=~@io_uring
    -p SystemCallFilter=~keyctl -p SystemCallFilter=~add_key -p SystemCallFilter=~request_key
    -p SystemCallErrorNumber=EPERM)

  if command -v systemd-run >/dev/null && [ -n "${XDG_RUNTIME_DIR:-}" ]; then
    printf 'launching under seccomp scope: %q ' "${ARGS[@]}"; echo
    exec "${ARGS[@]}" /usr/bin/Telegram "$@"
  else
    echo "WARNING: no user systemd-run; launching WITHOUT seccomp (AppArmor only)" >&2
    exec /usr/bin/Telegram "$@"
  fi

  .desktop 就回到乾淨一行:Exec=.../ansible_telegram_seccomp %u(env 的 --unset / LIBGL_ALWAYS_SOFTWARE=1 也一起搬進 wrapper,更好讀)。

  幾個要點:
  - wrapper 不能取名 Telegram(會 shadow /usr/bin/Telegram,正是你剛刪掉那個);用 ansible_telegram_seccomp 之類。
  - seccomp filter 會跨 execve 繼承(no_new_privs),所以 profile 註解講的 Telegram 自我 re-exec(/usr/bin/Telegram ix,updater/crash recovery)仍在 filter 內;AppArmor 也照 path 重新 attach。兩層都活著。
  - ~/.local/bin/ 的 wrapper 被 local_mixin_deny_persistent_attack 的 audit deny @{HOME}/.local/bin/{,*} w 保護 → 被打穿的 Telegram 改不動自己的 launcher,剛好是對的。

  ---
  要不要我直接做?步驟會是:

  1. 新增 roles/apparmor/templates/telegram/ansible_telegram_seccomp.sh.j2 + 部署 task(帶 managed header)。
  2. 改 ansible_telegram.desktop.j2 的 Exec= 指到 wrapper;把 env 搬進 wrapper。
  3. make apparmor-sandbox 自己跑過再回報。

  先講清楚:seccomp allowlist 我會預設 MODE=log(只記錄不阻擋)交付,讓你實機點一輪 Telegram(傳檔、視訊、貼圖、開連結)收集 journalctl --user 的 syscall denial,確認不誤殺再把預設翻成 enforce — 跟你 apparmor_profile_mode 的 complain→enforce
  同個節奏。這樣可以嗎?

✻ Sautéed for 2m 38s

❯ 我覺得沒有必要搞判斷 systemd-run，就直接 .desktop 就好。而且我一直都是 enforce 的狀況跑的

● 你這兩個決定我都接受 — 砍掉 systemd-run 判斷/fallback、直接 enforce,本來就是把我加的複雜度拿掉,合理。

  但在我把那串塞進 .desktop 之前,有兩個 systemd 行為我不能用記憶猜(猜錯的後果剛好是最糟的「seccomp 靜默沒生效」,違反你 fail-loudly 原則),得先查上游文件確認:

  1. systemd-run --scope(.desktop 啟動器需要的同步模式)到底吃不吃 SystemCallFilter 這種 exec sandbox property — scope 的 process 是 systemd-run 自己 fork 的、不是 manager exec 的,sandbox 屬性很可能被忽略。
  2. .desktop 啟動器需要 allowlist + denylist 兩條 SystemCallFilter,而 -p SystemCallFilter= 重複給,是合併還是後者覆蓋(覆蓋的話 @system-service allowlist 就沒了)。

  讓我查證。

❯ 啊.... 但是這樣也有缺點是 terminal 無法直接執行

❯ 所以妳的方案也是可以

❯ 主要原本是因為我討厭分一大堆檔案，但這障聽起來不得已

● 你那句「terminal 無法直接執行」其實正是最關鍵的理由 — wrapper 的本質就是「一個指令,.desktop 跟 terminal 用的是同一個」,seccomp 兩邊都生效、不會 DRY 破裂。而且它就是一個檔案(一支 ~/.local/bin/ script),不是「分一大堆」。所以收斂到
  wrapper,我同意。

  不過我剛才要查的兩個 systemd 行為,對 wrapper 一樣成立(wrapper 內部還是 systemd-run),而且其中一個可能直接推翻設計,我先查清楚再給你最終版。讓我查證。

● Web Search("systemd-run --scope SystemCallFilter sandboxing properties ignored scope unit")
  ⎿  Did 1 search in 9s

● Web Search("systemd scope unit does not support exec sandboxing SystemCallFilter RestrictAddressFamilies")
  ⎿  Did 1 search in 8s

● 第一個問題查實了:exec sandboxing(SystemCallFilter / RestrictAddressFamilies)只在 service unit 生效,scope unit 不支援 — 也就是說 systemd-run --scope 套 seccomp 會是靜默無效(或直接報錯)。所以 --scope 出局,必須用 transient
  service。這正是「不能用記憶猜」會踩到的雷。

  我再查 systemd-run(1) 的權威行為(service 模式的 env 繼承、--pipe/--wait、以及重複 -p SystemCallFilter 是否合併),確定最終 wrapper 寫法。

● Fetch(https://man.archlinux.org/man/systemd-run.1.en)
  ⎿  Received 36.3KB (200 OK)

● 查證有結果,而且其中一個直接改變設計 — 先講重點。

  查證結果(都會影響 wrapper,不只 .desktop)

  1. --scope 套不了 seccomp。 exec sandboxing(SystemCallFilter / RestrictAddressFamilies)是 service unit 專屬;scope 的 process 是 systemd-run 自己 fork、不經 manager 的 exec 路徑,所以這些屬性對 scope 無效(甚至報錯)。→ 必須用 transient
● Web Search("systemd-run --scope SystemCallFilter sandboxing properties ignored scope unit")
  ⎿  Did 1 search in 9s

● Web Search("systemd scope unit does not support exec sandboxing SystemCallFilter RestrictAddressFamilies")
  ⎿  Did 1 search in 8s

● 第一個問題查實了:exec sandboxing(SystemCallFilter / RestrictAddressFamilies)只在 service unit 生效,scope unit 不支援 — 也就是說 systemd-run
  --scope 套 seccomp 會是靜默無效(或直接報錯)。所以 --scope 出局,必須用 transient service。這正是「不能用記憶猜」會踩到的雷。

  我再查 systemd-run(1) 的權威行為(service 模式的 env 繼承、--pipe/--wait、以及重複 -p SystemCallFilter 是否合併),確定最終 wrapper 寫法。

● Fetch(https://man.archlinux.org/man/systemd-run.1.en)
  ⎿  Received 36.3KB (200 OK)

● 查證有結果,而且其中一個直接改變設計 — 先講重點。

  查證結果(都會影響 wrapper,不只 .desktop)

  1. --scope 套不了 seccomp。 exec sandboxing(SystemCallFilter / RestrictAddressFamilies)是 service unit 專屬;scope 的 process 是 systemd-run 自己

● 查證有結果,而且其中一個直接改變設計 — 先講重點。

  查證結果(都會影響 wrapper,不只 .desktop)

  1. --scope 套不了 seccomp。 exec sandboxing(SystemCallFilter / RestrictAddressFamilies)是 service unit 專屬;scope 的 process 是 systemd-run 自己 fork、不經 manager 的 exec 路徑,所以這些屬性對 scope 無效(甚至報錯)。→ 必須用 transient
● Web Search("systemd-run --scope SystemCallFilter sandboxing properties ignored scope unit")
  ⎿  Did 1 search in 9s

● Web Search("systemd scope unit does not support exec sandboxing SystemCallFilter RestrictAddressFamilies")
  ⎿  Did 1 search in 8s

● 第一個問題查實了:exec sandboxing(SystemCallFilter / RestrictAddressFamilies)只在 service unit 生效,scope unit 不支援 — 也就是說 systemd-run
  --scope 套 seccomp 會是靜默無效(或直接報錯)。所以 --scope 出局,必須用 transient service。這正是「不能用記憶猜」會踩到的雷。

  我再查 systemd-run(1) 的權威行為(service 模式的 env 繼承、--pipe/--wait、以及重複 -p SystemCallFilter 是否合併),確定最終 wrapper 寫法。

● Fetch(https://man.archlinux.org/man/systemd-run.1.en)
  ⎿  Received 36.3KB (200 OK)

● 查證有結果,而且其中一個直接改變設計 — 先講重點。

  查證結果(都會影響 wrapper,不只 .desktop)

  1. --scope 套不了 seccomp。 exec sandboxing(SystemCallFilter / RestrictAddressFamilies)是 service unit 專屬;scope 的 process 是 systemd-run 自己
● 查證有結果,而且其中一個直接改變設計 — 先講重點。

  查證結果(都會影響 wrapper,不只 .desktop)

  1. --scope 套不了 seccomp。 exec sandboxing(SystemCallFilter / RestrictAddressFamilies)是 service unit 專屬;scope 的 process 是 systemd-run 自己 fork、不經 manager 的 exec 路徑,所以這些屬性對 scope 無效(甚至報錯)。→ 必須用 transient
  ⎿  Did 1 search in 9s

● Web Search("systemd scope unit does not support exec sandboxing SystemCallFilter RestrictAddressFamilies")
  ⎿  Did 1 search in 8s

● 第一個問題查實了:exec sandboxing(SystemCallFilter / RestrictAddressFamilies)只在 service unit 生效,scope unit 不支援 — 也就是說 systemd-run
  --scope 套 seccomp 會是靜默無效(或直接報錯)。所以 --scope 出局,必須用 transient service。這正是「不能用記憶猜」會踩到的雷。

  我再查 systemd-run(1) 的權威行為(service 模式的 env 繼承、--pipe/--wait、以及重複 -p SystemCallFilter 是否合併),確定最終 wrapper 寫法。

● Fetch(https://man.archlinux.org/man/systemd-run.1.en)
  ⎿  Received 36.3KB (200 OK)

● 查證有結果,而且其中一個直接改變設計 — 先講重點。

  查證結果(都會影響 wrapper,不只 .desktop)

  1. --scope 套不了 seccomp。 exec sandboxing(SystemCallFilter / RestrictAddressFamilies)是 service unit 專屬;scope 的 process 是 systemd-run 自己
  fork、不經 manager 的 exec 路徑,所以這些屬性對 scope 無效(甚至報錯)。→ 必須用 transient service(systemd-run 預設模式,不加 --scope)。
  2. service 不繼承呼叫者的環境。 它在「乾淨、detached、parent 是 service manager」的環境跑,所以 GUI 需要的 WAYLAND_DISPLAY / DISPLAY /
  XDG_RUNTIME_DIR / DBUS_SESSION_BUS_ADDRESS 等要顯式帶進去(-E VAR 不給值時會抓呼叫端同名變數的現值)。

  好消息:service + --pipe --wait 剛好把你那句「terminal 無法直接執行」完全解掉 — 在 terminal 打 wrapper 會像直接跑 app 一樣:阻塞、stdout/stderr
  直接顯示;.desktop 用同一支也一樣。一支檔案、兩邊同源、seccomp 兩邊都生效。所以你的 terminal 疑慮不但沒了,還是選 wrapper 的決定性理由。

● 查證有結果,而且其中一個直接改變設計 — 先講重點。

  查證結果(都會影響 wrapper,不只 .desktop)

● 查證有結果,而且其中一個直接改變設計 — 先講重點。

  查證結果(都會影響 wrapper,不只 .desktop)

  1. --scope 套不了 seccomp。 exec sandboxing(SystemCallFilter / RestrictAddressFamilies)是 service unit 專屬;scope 的 process 是 systemd-run 自己 fork、不經 manager 的 exec 路徑,所以這些屬性對 scope 無效(甚至報錯)。→ 必須用 transient
  service(systemd-run 預設模式,不加 --scope)。
  2. service 不繼承呼叫者的環境。 它在「乾淨、detached、parent 是 service manager」的環境跑,所以 GUI 需要的 WAYLAND_DISPLAY / DISPLAY / XDG_RUNTIME_DIR / DBUS_SESSION_BUS_ADDRESS 等要顯式帶進去(-E VAR 不給值時會抓呼叫端同名變數的現值)。

  好消息:service + --pipe --wait 剛好把你那句「terminal 無法直接執行」完全解掉 — 在 terminal 打 wrapper 會像直接跑 app 一樣:阻塞、stdout/stderr 直接顯示;.desktop 用同一支也一樣。一支檔案、兩邊同源、seccomp 兩邊都生效。所以你的 terminal
  疑慮不但沒了,還是選 wrapper 的決定性理由。

  驗證過的 wrapper 形狀(就一個檔案)

  #!/bin/bash
  # =============================================================================
  # MANAGED BY ANSIBLE - DO NOT EDIT MANUALLY
  #   src: roles/apparmor/templates/telegram/<this>.j2
  # =============================================================================
  set -euo pipefail

  # Forward only the GUI vars a transient --user service needs (it does NOT inherit
  # the caller env). Conditional so an unset var (e.g. DISPLAY on pure Wayland) is skipped.
  ENV_FWD=()
  for v in WAYLAND_DISPLAY DISPLAY XAUTHORITY XDG_RUNTIME_DIR \
           DBUS_SESSION_BUS_ADDRESS XDG_CURRENT_DESKTOP XDG_SESSION_TYPE; do
    [ -n "${!v:-}" ] && ENV_FWD+=(-E "$v")
  done

  CMD=(systemd-run --user --pipe --wait --collect "${ENV_FWD[@]}"
    -p SystemCallArchitectures=native           # close the 32-bit/x32 ABI seccomp bypass
    -p SystemCallErrorNumber=EPERM              # denied syscall -> EPERM, not SIGSYS-kill (fail-soft)
    # Denylist: kill exactly the LPE primitives AppArmor CANNOT mediate. Telegram uses none of these.
    -p 'SystemCallFilter=~userfaultfd perf_event_open keyctl add_key request_key @io_uring @obsolete @cpu-emulation @raw-io @swap @reboot @module @debug'
    /usr/bin/env --unset=LD_LIBRARY_PATH --unset=PYTHONPATH LIBGL_ALWAYS_SOFTWARE=1
    /usr/bin/Telegram)

  printf 'launching under seccomp: %q ' "${CMD[@]}"; echo   # transparency: print before exec
  exec "${CMD[@]}" "$@"

  .desktop 回到乾淨一行:Exec=<wrapper> %u。

  一個要對你誠實的點:這是 denylist,不是 allowlist

  - 我刻意用 denylist(~...)而不是 allowlist(@system-service):後者更強,但會 EPERM 掉任何沒列進去的 syscall,沒有 log 驗證輪就直接 enforce 很可能弄壞 Telegram;你說你一律 enforce、不跑驗證,denylist 才合你的流程(只擋我列的那幾個,Telegram
  正常用不到 → 幾乎不可能誤殺)。
  - 它的價值範圍要講清楚:精準幹掉 AppArmor 碰不到的那批 LPE primitive(userfaultfd / perf_event_open / keyring syscalls / io_uring setup / obsolete・debug 家族)。它不會把所有 syscall 都沙箱化 — setsockopt/futex/ioctl 這種 Telegram
  本來就要用的,allowlist 也擋不掉。所以這是「補上 AppArmor 的 syscall 盲區」,不是「萬能沙箱」。日後想升級 allowlist,再走一次 SystemCallLog= 收集即可。
  - 單一 SystemCallFilter 指派(一條),順便避開「重複 -p 到底合併還覆蓋」那個我查不到明確文件、猜錯會靜默砍掉 allowlist 的坑。

  ---
  要我直接做嗎?步驟:

  1. 新增 roles/apparmor/templates/telegram/<wrapper>.sh.j2 + 部署 task(managed header、0755)。
  2. 改 ansible_telegram.desktop.j2:Exec= 指到 wrapper(env 搬進 wrapper)。
  3. 把舊的 idempotence 移除清單沿用(新名字不撞 Telegram/telegram-desktop)。
  4. make apparmor-sandbox 自己跑過回報。

  唯一要你定的偏好:wrapper 取名(會放 ~/.local/bin/,你會在 terminal 打它)。建議 telegram(小寫,不會 shadow /usr/bin/Telegram,也不撞 idempotence 移除清單裡的 telegram-desktop);或你想要更短的 tg / 更白的 telegram-seccomp?

  Sources:
  - systemd/Sandboxing - ArchWiki (https://wiki.archlinux.org/title/Systemd/Sandboxing)
  - ServiceSandboxing - Debian Wiki (https://wiki.debian.org/ServiceSandboxing)
  - systemd-run(1) - Arch manual pages (https://man.archlinux.org/man/systemd-run.1.en)

✻ Baked for 7m 44s

※ recap: Goal: harden the Telegram AppArmor profile against kernel exploits by adding a seccomp layer. We settled on a single `~/.local/bin/` wrapper using a transient systemd-run service (scope can't do seccomp). Next: you pick the
  wrapper name, then I build it. (disable recaps in /config)
