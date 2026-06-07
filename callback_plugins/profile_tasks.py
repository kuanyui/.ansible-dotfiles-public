"""Lightweight task run/skip log + timing callback for ansible-core (no collection deps).

Enable via:
    ANSIBLE_CALLBACKS_ENABLED=profile_tasks ansible-playbook ...
Or in ansible.cfg:
    [defaults]
    callbacks_enabled = profile_tasks

At the end of the run it prints, in this order:
  1. a boot-style log of EVERY task in execution order, each tagged like systemd
     boot: [  OK  ] ran, [ SKIP ] skipped (e.g. `when:` false), [ FAIL ] failed;
  2. a sorted top-N list of the slowest tasks by elapsed wall time, plus a total.

Roughly equivalent to ansible.posix.profile_tasks but written from scratch so this
repo's "ansible-core only, no collections" rule (top-level CLAUDE.md) is not violated.
"""

from __future__ import annotations

import time
from typing import Any

from ansible.plugins.callback import CallbackBase

DOCUMENTATION = """
    name: profile_tasks
    callback_type: aggregate
    short_description: Boot-style run/skip log + task timings (ansible-core-only variant).
    description:
        - Lightweight equivalent of ansible.posix.profile_tasks, implemented
          locally to keep this project's "ansible-core only, no collections"
          rule intact.
        - At the end of the run prints every task in execution order with a
          systemd-boot-style status tag ([  OK  ] / [ SKIP ] / [ FAIL ]), then a
          sorted top-N list of tasks by elapsed wall time.
    requirements:
        - Enabled via ANSIBLE_CALLBACKS_ENABLED env var or callbacks_enabled
          in ansible.cfg.
"""


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = "aggregate"
    CALLBACK_NAME = "profile_tasks"
    CALLBACK_NEEDS_ENABLED = True

    TOP_N = 30  # how many slowest tasks to print at the end (-1 = all)

    # Boot-style status tags, fixed 8-wide so the task names line up (like systemd).
    # Color is per-status; None = the terminal's default (skips stay muted).
    _STATUS_TAG = {"ok": "[  OK  ]", "skip": "[ SKIP ]", "fail": "[ FAIL ]"}
    _STATUS_COLOR: dict[str, str | None] = {"ok": "green", "skip": None, "fail": "red"}

    def __init__(self) -> None:
        super().__init__()
        self._task_start: float | None = None
        self._current_task: str | None = None
        self._timings: list[tuple[str, float]] = []
        # Run/skip log: one record ({name, status}) per task as it STARTS, so the
        # final list is in execution order. The runner_on_* hooks upgrade the
        # current record's status. Default "skip" so a task whose `when:` was false
        # (only runner_on_skipped fires, or nothing does) stays SKIP.
        self._results: list[dict[str, str]] = []
        self._current_result: dict[str, str] | None = None

    def _record_pending(self) -> None:
        if self._task_start is None or self._current_task is None:
            return
        elapsed = time.monotonic() - self._task_start
        self._timings.append((self._current_task, elapsed))

    def _begin_task(self, name: str) -> None:
        self._record_pending()
        self._task_start = time.monotonic()
        self._current_task = name
        self._current_result = {"name": name, "status": "skip"}
        self._results.append(self._current_result)

    def _mark(self, status: str) -> None:
        # Precedence: fail > ok > skip. Never downgrade (e.g. ok-on-host1 +
        # skip-on-host2 stays OK; any failure wins).
        if self._current_result is None:
            return
        if self._current_result["status"] == "fail":
            return
        if status == "fail" or self._current_result["status"] != "ok":
            self._current_result["status"] = status

    def v2_playbook_on_task_start(self, task: Any, is_conditional: bool) -> None:
        self._begin_task(task.get_name().strip() or "<unnamed task>")

    def v2_playbook_on_handler_task_start(self, task: Any) -> None:
        self._begin_task(f"[handler] {task.get_name().strip() or '<unnamed handler>'}")

    def v2_runner_on_ok(self, result: Any) -> None:
        self._mark("ok")

    def v2_runner_on_failed(self, result: Any, ignore_errors: bool = False) -> None:
        self._mark("fail")

    def v2_runner_on_unreachable(self, result: Any) -> None:
        self._mark("fail")

    def v2_runner_on_skipped(self, result: Any) -> None:
        self._mark("skip")

    def v2_playbook_on_stats(self, stats: Any) -> None:
        self._record_pending()

        # 1) Boot-style run/skip log, in EXECUTION ORDER, before the timings.
        self._display.display("")
        self._display.banner(f"TASK RESULTS  ({len(self._results)} tasks, in execution order)")
        for record in self._results:
            tag = self._STATUS_TAG.get(record["status"], "[ ???? ]")
            self._display.display(f"{tag} {record['name']}", color=self._STATUS_COLOR.get(record["status"]))

        # 2) Slowest-tasks timing summary.
        self._timings.sort(key=lambda x: x[1], reverse=True)
        top = self._timings if self.TOP_N < 0 else self._timings[: self.TOP_N]
        total = sum(s for _, s in self._timings)
        self._display.display("")
        self._display.banner(f"TASK TIMINGS  (top {len(top)} of {len(self._timings)} tasks, by elapsed)")
        for name, secs in top:
            self._display.display(f"  {secs:8.2f}s  {name}")
        self._display.display("-" * 72)
        self._display.display(f"  {total:8.2f}s  TOTAL")
