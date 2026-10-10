"""Bracket helpers shared by the string scanners (no dependencies on the rest of the package)."""

from __future__ import annotations

OPENING_BRACKETS = "([{"
CLOSING_BRACKETS = ")]}"
GROUPING = OPENING_BRACKETS + CLOSING_BRACKETS


def find_matching_parenthesis(string: str, index: int, delimiters: tuple[str, str] = ("(", ")")) -> int:
    """Index of the delimiter closing the one at (or first after) ``index``; ``-1`` if unclosed."""
    opening, closing = delimiters
    depth = 0
    for k in range(index, len(string)):
        if string[k] == opening:
            depth += 1
        elif string[k] == closing:
            depth -= 1
            if depth == 0:
                return k
    return -1
