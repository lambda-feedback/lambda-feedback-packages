"""Implicit-multiplication conventions: how ``a/bc`` groups."""

from __future__ import annotations

from functools import cache

from lambdafeedback.slr_parsing import SLRError, SLRParser, build_expression_parser, compose, group, infix

from .errors import ExpressionParsingError
from .params import Convention, validate_convention


@cache
def convention_parser(convention: Convention) -> SLRParser:
    """A parser that makes a convention's grouping explicit (built once per convention).

    With ``"equal_precedence"`` implicit multiplication binds like ``*`` and
    ``/`` (``a/bc`` is ``a/b*c``); with ``"implicit_higher_precedence"`` it
    binds tighter (``a/bc`` is ``a/(bc)``).
    """
    validate_convention(convention)
    custom_tokens = [(r" *(\*|\+|-| ) *", "SPLIT"), (" */ *", "SOLIDUS")]
    custom_productions = [("E", "*E", group(2, empty=True)), ("E", "EE", group(2, empty=True))]
    if convention == "equal_precedence":
        custom_productions.append(("E", "E/E", infix))
    else:
        custom_productions.append(("E", "E/E", compose(infix, group(1, empty=True, delimiters=["(", ")"]))))
    return build_expression_parser(
        delimiters=[(("(", ")"), group(1))],
        undefined=("O", "OTHER"),
        expression_node=("E", "EXPRESSION_NODE"),
        custom_tokens=custom_tokens,
        custom_productions=custom_productions,
    )


def apply_convention(expression: str, convention: Convention | None) -> str:
    """Rewrite ``expression`` with the convention's grouping made explicit (``None``: unchanged).

    Raises :class:`ExpressionParsingError` if ``expression`` can't be parsed (e.g. ``a/``).
    """
    if convention is None:
        return expression
    parser = convention_parser(convention)
    try:
        return str(parser.parse(parser.scan(expression))[0].content_string())
    except SLRError as e:
        raise ExpressionParsingError(f"Failed to parse expression {expression!r}: {e}", expression=expression) from e
