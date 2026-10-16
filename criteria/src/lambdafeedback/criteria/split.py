"""Splitting a string of criteria, such as ``response = answer, response > 0``, into criteria."""

from __future__ import annotations

from .errors import CriteriaSyntaxError

_OPENING = {")": "(", "]": "[", "}": "{"}
"""The opening bracket for each closing bracket."""


def split_criteria(criteria: str) -> list[str]:
    """``criteria`` split on the commas outside brackets, with each criterion stripped.

    Each kind of bracket (``()``, ``[]``, ``{}``) is counted on its own. Raises
    :class:`CriteriaSyntaxError` if a bracket is closed before it is opened,
    or left open.
    """
    depth = dict.fromkeys(_OPENING.values(), 0)
    parts = []
    start = 0
    for index, char in enumerate(criteria):
        if char in depth:
            depth[char] += 1
        elif char in _OPENING:
            opening = _OPENING[char]
            if depth[opening] == 0:
                raise CriteriaSyntaxError(f"`{char}` at position {index} closes no `{opening}` in: {criteria}")
            depth[opening] -= 1
        elif char == "," and not any(depth.values()):
            parts.append(criteria[start:index].strip())
            start = index + 1
    if any(depth.values()):
        raise CriteriaSyntaxError(f"Unclosed bracket in: {criteria}")
    parts.append(criteria[start:].strip())
    return parts
