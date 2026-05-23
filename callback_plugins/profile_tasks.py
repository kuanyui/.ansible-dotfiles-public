"""Lightweight task-timing callback for ansible-core (no collection deps).

Enable via:
    ANSIBLE_CALLBACKS_ENABLED=profile_tasks ansible-playbook ...
Or in ansible.cfg:
    [defaults]
    callbacks_enabled = profile_tasks

Prints a sorted top-N list of tasks by elapsed wall time, plus a total,
when the playbook finishes. Roughly equivalent to ansible.posix.profile_tasks
but written from scratch so this repo's "ansible-core only, no collections"
rule (top-level CLAUDE.md) is not violated.
"""

from __future__ import annotations

import time
from typing import Any

from ansible.plugins.callback import CallbackBase

DOCUMENTATION = """
    name: profile_tasks
    callback_type: aggregate
    short_description: Adds elapsed-time info to tasks (ansible-core-only variant).
    description:
        - Lightweight equivalent of ansible.posix.profile_tasks, implemented
          locally to keep this project's "ansible-core only, no collections"
          rule intact.
        - Prints a sorted top-N list of tasks by elapsed wall time at the
          end of the run.
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

    def __init__(self) -> None:
        super().__init__()
        self._task_start: float | None = None
        self._current_task: str | None = None
        self._timings: list[tuple[str, float]] = []

    def _record_pending(self) -> None:
        if self._task_start is None or self._current_task is None:
            return
        elapsed = time.monotonic() - self._task_start
        self._timings.append((self._current_task, elapsed))

    def v2_playbook_on_task_start(self, task: Any, is_conditional: bool) -> None:
        self._record_pending()
        self._task_start = time.monotonic()
        self._current_task = task.get_name().strip() or "<unnamed task>"

    def v2_playbook_on_handler_task_start(self, task: Any) -> None:
        self._record_pending()
        self._task_start = time.monotonic()
        name = task.get_name().strip() or "<unnamed handler>"
        self._current_task = f"[handler] {name}"

    def v2_playbook_on_stats(self, stats: Any) -> None:
        self._record_pending()
        self._timings.sort(key=lambda x: x[1], reverse=True)

        top = self._timings if self.TOP_N < 0 else self._timings[: self.TOP_N]
        total = sum(s for _, s in self._timings)

        # Use self._display.display so the lines go through ansible's
        # display layer (same channel as the stdout_callback). Plain
        # print() can be hidden when ansible buffers or routes stdout
        # elsewhere.
        self._display.display("")
        self._display.banner(f"TASK TIMINGS  (top {len(top)} of {len(self._timings)} tasks, by elapsed)")
        for name, secs in top:
            self._display.display(f"  {secs:8.2f}s  {name}")
        self._display.display("-" * 72)
        self._display.display(f"  {total:8.2f}s  TOTAL")
