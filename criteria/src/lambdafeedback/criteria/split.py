"""Splitting a string of criteria, such as ``response = answer, response > 0``, into criteria."""

from __future__ import annotations

from .errors import CriteriaSyntaxError

_OPENING = frozenset("([{")
_CLOSING = frozenset(")]}")


def split_criteria(criteria: str) -> list[str]:
    """``criteria`` split on the commas outside brackets, with each criterion stripped.

    Any closing bracket (``)``, ``]``, ``}``) closes any opening one, so
    half-open intervals such as ``x in [0, 1)`` keep their comma. Raises
    :class:`CriteriaSyntaxError` if a bracket is closed when none is open,
    or left open, or if a criterion is empty (``a = b,`` or ``a = b,, c = d``).
    """
    depth = 0
    parts = []
    start = 0
    for index, char in enumerate(criteria):
        if char in _OPENING:
            depth += 1
        elif char in _CLOSING:
            if depth == 0:
                raise CriteriaSyntaxError(f"`{char}` at position {index} closes no bracket in: {criteria}")
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(_criterion(criteria, start, index))
            start = index + 1
    if depth:
        raise CriteriaSyntaxError(f"Unclosed bracket in: {criteria}")
    parts.append(_criterion(criteria, start, len(criteria)))
    return parts


def _criterion(criteria: str, start: int, end: int) -> str:
    """``criteria[start:end]``, stripped; raises :class:`CriteriaSyntaxError` if that leaves nothing."""
    criterion = criteria[start:end].strip()
    if not criterion:
        raise CriteriaSyntaxError(f"Empty criterion at position {start} in: {criteria}")
    return criterion
