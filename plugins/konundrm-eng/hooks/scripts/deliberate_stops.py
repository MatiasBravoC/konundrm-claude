"""Recognizes the line a session writes to stop on purpose: ``RED:`` (a handoff) or ``BLOCKED:``.

The stop gate lets a turn end on a red tree only with such a line, and run_slices.py stops chaining
sessions on one, so both read it through this one definition. The line starts with ``RED`` or
``BLOCKED`` in capitals followed by a colon, after any Markdown decoration: indentation, a quote
``>``, a list ``-``, a heading ``#``, emphasis (``**BLOCKED:**``, ``**BLOCKED**:``) or code marks.
The words anywhere else in a line (``the test went RED: then green``) are not a stop.
"""

from __future__ import annotations

import re

DELIBERATE_STOP = re.compile(r"(?m)^[\s>*_`#-]*(?P<kind>RED|BLOCKED)\b\**:[*_`]*")
"""A stop line's marker with its decoration; the emphasis or code mark closing it is included."""


def find_deliberate_stop(text: str) -> str | None:
    """Finds the first line in a text that stops on purpose, without its Markdown decoration.

    Args:
        text: A session's output or final message, one or more lines.

    Returns:
        ``RED: <rest of the line>`` or ``BLOCKED: <rest of the line>`` for the first stop line,
        with the decoration around the marker removed and the rest stripped (``**BLOCKED:** T2
        needs a plan change`` gives ``BLOCKED: T2 needs a plan change``); None when no line is one.
    """
    marker = DELIBERATE_STOP.search(text)
    if marker is None:
        return None
    reason = text[marker.end() :].split("\n", 1)[0].strip()
    return f"{marker.group('kind')}: {reason}".rstrip()
