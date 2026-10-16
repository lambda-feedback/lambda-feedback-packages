"""Grammar and parser for criteria on physical quantities, such as ``response matches answer``.

Criteria compare two quantities with ``matches``, ``=``, ``<=``, ``>=``,
``<`` or ``>``, or compare their dimensions with
``dimension(QUANTITY) matches dimension(QUANTITY)``. ``response`` and
``answer`` scan as ``QUANTITY``; other text is ``INPUT``.
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
    create_node,
    infix,
    operate,
)

from .grammar import END_SYMBOL, NULL_SYMBOL, START_SYMBOL


def _spaced(form: str) -> Lexeme:
    """``form``, with any spaces around it."""
    return Lexeme((form,), space_before=True, space_after=True)


_OPERATORS = ("matches", "dimension", "=", "<=", ">=", "<", ">")

QUANTITY_TOKENS: tuple[TokenSpec, ...] = (
    TokenPattern(START_SYMBOL, START_SYMBOL),
    TokenPattern(END_SYMBOL, END_SYMBOL),
    TokenPattern(NULL_SYMBOL, NULL_SYMBOL),
    TokenPattern(_spaced("BOOL"), "BOOL"),
    TokenPattern(_spaced("QUANTITY"), "QUANTITY"),
    TokenPattern(_spaced("DIMENSION"), "DIMENSION"),
    TokenPattern(Lexeme(("(",), space_after=True), "START_DELIMITER"),
    TokenPattern(Lexeme((")",), space_before=True), "END_DELIMITER"),
    TokenPattern("response", "QUANTITY"),
    TokenPattern("answer", "QUANTITY"),
    CatchAll("INPUT", "INPUT"),
    # Operators are labelled with the spaces around them (e.g. `` matches ``), as in compareExpressions.
    *(TokenPattern(_spaced(operator), f" {operator} ") for operator in _OPERATORS),
)

QUANTITY_PRODUCTIONS: tuple[tuple[str, str, Action], ...] = (
    ("START", "BOOL", create_node),
    ("BOOL", "QUANTITY matches QUANTITY", infix),
    ("BOOL", "DIMENSION matches DIMENSION", infix),
    ("BOOL", "QUANTITY=QUANTITY", infix),
    ("BOOL", "QUANTITY<=QUANTITY", infix),
    ("BOOL", "QUANTITY>=QUANTITY", infix),
    ("BOOL", "QUANTITY<QUANTITY", infix),
    ("BOOL", "QUANTITY>QUANTITY", infix),
    ("QUANTITY", "INPUT", create_node),
    ("DIMENSION", "dimension(QUANTITY)", operate(1)),
)


def build_quantity_criteria_parser(
    reserved_expressions: Mapping[str, Mapping[str, Any]],
    token_list: Sequence[TokenSpec] = QUANTITY_TOKENS,
    productions: Sequence[tuple[str, str, Action | None]] = QUANTITY_PRODUCTIONS,
) -> SLRParser:
    """A parser for criteria on physical quantities.

    Takes the same arguments as :func:`.build_criteria_parser`, so either can
    be used where a criteria parser is built from the reserved expressions.
    ``reserved_expressions`` isn't used yet: only ``response`` and ``answer``
    scan as ``QUANTITY``.
    """
    return SLRParser(token_list, productions, START_SYMBOL, END_SYMBOL, NULL_SYMBOL)
