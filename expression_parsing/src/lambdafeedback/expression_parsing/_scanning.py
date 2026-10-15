"""Helpers shared by the string scanners (no dependencies on the rest of the package)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeAlias

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


Match: TypeAlias = tuple[int, int, str]
"""``(start, end, replacement)``: replace ``text[start:end]`` by ``replacement``."""


def replace_matches(text: str, find: Callable[[str, int], Match | None]) -> str:
    """Replace each match ``find(text, index)`` reports, left to right.

    ``find`` returns the first match starting at or after ``index`` (or
    ``None``) and must end after ``index``; scanning resumes at the match's
    end, so replacements are never scanned again.
    """
    pieces = []
    done = 0
    while (match := find(text, done)) is not None:
        start, end, replacement = match
        pieces += [text[done:start], replacement]
        done = end
    pieces.append(text[done:])
    return "".join(pieces)
