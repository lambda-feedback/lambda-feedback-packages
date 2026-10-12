"""Grammar and parser for criteria such as ``response = answer where a = 2``.

Criteria are equalities and orderings between expressions, optionally with
``where`` substitutions, plus ``written as``, ``proportional to`` and
``contains``. Names from the reserved expressions (``response``,
``answer``, ...) scan as ``RESERVED``; other text is ``OTHER``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from lambdafeedback.slr_parsing import (
    Action,
    CatchAll,
    Lexeme,
    SLRParser,
    TokenPattern,
    TokenSpec,
    append_last,
    create_node,
    infix,
    join,
    proceed,
)

START_SYMBOL = "START"
END_SYMBOL = "END"
NULL_SYMBOL = "NULL"


def _spaced(*forms: str) -> Lexeme:
    """Any of ``forms``, with any spaces around it."""
    return Lexeme(forms, space_before=True, space_after=True)


TOKENS: tuple[TokenSpec, ...] = (
    TokenPattern(START_SYMBOL, START_SYMBOL),
    TokenPattern(END_SYMBOL, END_SYMBOL),
    TokenPattern(NULL_SYMBOL, NULL_SYMBOL),
    TokenPattern(_spaced("BOOL"), "BOOL"),
    TokenPattern(_spaced("EQUALITY"), "EQUALITY"),
    TokenPattern(_spaced("EQUAL"), "EQUAL"),
    TokenPattern(_spaced("EQUAL_LIST"), "EQUAL_LIST"),
    TokenPattern(_spaced("RESERVED"), "RESERVED"),
    TokenPattern(_spaced("="), "EQUALITY"),
    TokenPattern(_spaced(">=", ">", "<=", "<", "ORDER"), "ORDER"),
    TokenPattern(_spaced("where"), "WHERE"),
    TokenPattern(_spaced("written as"), "WRITTEN_AS"),
    TokenPattern(_spaced("proportional to"), "PROPORTIONAL_TO"),
    TokenPattern(_spaced("contains"), "CONTAINS"),
    TokenPattern(_spaced(";"), "SEPARATOR"),
    CatchAll(_spaced("OTHER"), "OTHER"),
)

# Order matters: when productions conflict, the one listed later wins.
_OPERANDS = ("OTHER", "RESERVED")


def _relation(head: str, operator: str) -> tuple[tuple[str, str, Action], ...]:
    """``head -> left operator right`` for every combination of ``OTHER``/``RESERVED`` operands."""
    return tuple((head, f"{left}{operator}{right}", infix) for right in _OPERANDS for left in _OPERANDS)


def _reserved_relation(head: str, operator: str) -> tuple[tuple[str, str, Action], ...]:
    """``head -> RESERVED operator right``, with an ``OTHER`` or ``RESERVED`` right operand."""
    return tuple((head, f"RESERVED{operator}{right}", infix) for right in _OPERANDS)


PRODUCTIONS: tuple[tuple[str, str, Action], ...] = (
    ("START", "BOOL", create_node),
    ("BOOL", "EQUAL", proceed),
    ("BOOL", "ORDER", proceed),
    ("BOOL", "EQUAL where EQUAL", infix),
    ("BOOL", "EQUAL where EQUAL_LIST", infix),
    *_reserved_relation("BOOL", " written as "),
    *_relation("EQUAL", " proportional to "),
    *_reserved_relation("BOOL", " contains "),
    ("EQUAL_LIST", "EQUAL;EQUAL", infix),
    ("EQUAL_LIST", "EQUAL_LIST;EQUAL", append_last),
    *_relation("EQUAL", " = "),
    *_relation("EQUAL", " ORDER "),
    ("OTHER", "RESERVED OTHER", join),
    ("OTHER", "OTHER RESERVED", join),
    ("OTHER", "OTHER OTHER", join),
)


def build_criteria_parser(
    reserved_expressions: Mapping[str, Mapping[str, Any]],
    token_list: Sequence[TokenSpec] = TOKENS,
    productions: Sequence[tuple[str, str, Action | None]] = PRODUCTIONS,
) -> SLRParser:
    """A parser for criteria, where the keys of each reserved-expression group scan as ``RESERVED``.

    ``reserved_expressions`` maps groups (e.g. ``"learner"``, ``"task"``) to
    ``{name: expression}``; only the names are used here.
    """
    reserved = [TokenPattern(name, "RESERVED") for group in reserved_expressions.values() for name in group]
    return SLRParser([*token_list, *reserved], productions, START_SYMBOL, END_SYMBOL, NULL_SYMBOL)
