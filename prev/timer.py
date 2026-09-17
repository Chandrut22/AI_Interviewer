"""Timed answer capture.

`select.select()` on stdin does not work on Windows, so the primary path uses
prompt_toolkit's asyncio prompt wrapped in `asyncio.wait_for`. On timeout the
text the candidate had already typed is salvaged from the session buffer and
returned with `timed_out=True`, so a slow answer can be scored differently from
a wrong one.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML


@dataclass
class Answer:
    text: str
    elapsed_s: float
    timed_out: bool


def ask_timed(prompt_label: str, limit_s: int) -> Answer:
    try:
        return asyncio.run(_ask_prompt_toolkit(prompt_label, limit_s))
    except ImportError:
        return _ask_plain(limit_s)


async def _ask_prompt_toolkit(prompt_label: str, limit_s: int) -> Answer:


    session: PromptSession = PromptSession()
    deadline = time.monotonic() + limit_s
    started = time.monotonic()

    def toolbar() -> HTML:
        left = max(0, int(round(deadline - time.monotonic())))
        warn = ' bg="#a32d2d"' if left <= 15 else ""
        return HTML(
            f"<b{warn}> {left // 60:d}:{left % 60:02d} left </b>"
            "  Alt+Enter (or Esc then Enter) to submit"
        )

    try:
        text = await asyncio.wait_for(
            session.prompt_async(
                HTML(f"<ansicyan>{prompt_label}</ansicyan> "),
                multiline=True,
                bottom_toolbar=toolbar,
                refresh_interval=0.4,
            ),
            timeout=limit_s,
        )
        return Answer(text.strip(), round(time.monotonic() - started, 1), False)
    except asyncio.TimeoutError:
        partial = ""
        try:
            partial = session.default_buffer.text
        except Exception:  # buffer torn down mid-cancel
            pass
        return Answer(partial.strip(), float(limit_s), True)


def _ask_plain(limit_s: int) -> Answer:
    """Fallback with no countdown: blocking input, elapsed time still recorded."""
    print(f"(no prompt_toolkit installed - soft limit {limit_s}s, blank line to submit)")
    started = time.monotonic()
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not line.strip():
            break
        lines.append(line)
    elapsed = round(time.monotonic() - started, 1)
    return Answer("\n".join(lines).strip(), elapsed, elapsed > limit_s)
