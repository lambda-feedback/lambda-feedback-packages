"""String-level preprocessing of responses before they are parsed."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from ._scanning import CLOSING_BRACKETS, GROUPING, OPENING_BRACKETS, find_matching_parenthesis
from .errors import AbsoluteValueNotationError, BracketNotationError, ExpressionParsingError
from .substitution import substitute_input_symbols
from .symbol_tables import MINUS_PLUS, PLUS_MINUS

if TYPE_CHECKING:
    from .params import ExpressionParams

_BRACKET_PAIRS = dict(zip(CLOSING_BRACKETS, OPENING_BRACKETS, strict=True))


def split_equation(expr: str, error: type[ExpressionParsingError]) -> list[str]:
    """``[expr]``, or ``[lhs, rhs]`` for an equation; raises ``error`` for more than one ``=``."""
    sides = expr.split("=")
    if len(sides) > 2:
        raise error(f"An expression can contain at most one '=': {expr}", expression=expr)
    return sides


def has_matching_brackets(expr: str) -> bool:
    """True if every ``(``, ``[``, ``{`` is closed by the same kind, correctly nested.

    Mismatched kinds (e.g. the ``[x+y)`` of interval notation) and unbalanced
    brackets are rejected.
    """
    stack = []
    for char in expr:
        if char in OPENING_BRACKETS:
            stack.append(char)
        elif char in CLOSING_BRACKETS and (not stack or stack.pop() != _BRACKET_PAIRS[char]):
            return False
    return not stack


def is_multiple_answers_wrapper(expr: str) -> bool:
    """True if ``expr`` as a whole is one top-level ``{...}``: a set of acceptable answers.

    Braces that merely sit at both ends (e.g. ``{x+1}*{x-2}``) don't count.
    """
    stripped = expr.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return False
    return find_matching_parenthesis(stripped, 0, delimiters=("{", "}")) == len(stripped) - 1


def create_expression_set(exprs: str | Sequence[str], params: ExpressionParams) -> list[str]:
    """Expand a response into the expressions it stands for.

    A top-level ``{a, b}`` gives one expression per element, and ``±``/``∓``
    (``plus_minus``/``minus_plus``) give both signs. Symbol aliases are
    substituted. The result is de-duplicated, in first-seen order.
    """
    if isinstance(exprs, str):
        exprs = (
            [e.strip() for e in _split_top_level(exprs.strip()[1:-1])]
            if is_multiple_answers_wrapper(exprs)
            else [exprs]
        )
    expanded: dict[str, None] = {}
    for original in exprs:
        # substitute_input_symbols also writes params.plus_minus/minus_plus as PLUS_MINUS/MINUS_PLUS.
        expr = substitute_input_symbols(original, params)
        expanded.update(dict.fromkeys(expand_plus_minus(expr)))
    return list(expanded)


def expand_plus_minus(expr: str) -> list[str]:
    """Both signs of an expression containing ``plus_minus``/``minus_plus`` (otherwise just ``expr``)."""
    if PLUS_MINUS not in expr and MINUS_PLUS not in expr:
        return [expr]
    signed = (
        expr.replace(PLUS_MINUS, plus_minus).replace(MINUS_PLUS, minus_plus).strip()
        for plus_minus, minus_plus in (("+", "-"), ("-", "+"))
    )
    return [s.lstrip("+").strip() for s in signed]


def _split_top_level(text: str) -> list[str]:
    """Split ``text`` at the commas that aren't inside brackets."""
    parts = []
    depth = start = 0
    for index, char in enumerate(text):
        if char in OPENING_BRACKETS:
            depth += 1
        elif char in CLOSING_BRACKETS:
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(text[start:index])
            start = index + 1
    parts.append(text[start:])
    return parts


def convert_bracket_notation(expr: str) -> str:
    """Accept ``[]`` and ``{}`` as grouping brackets by rewriting them as ``()``.

    SymPy reserves ``[]`` and ``{}`` for lists and sets. A ``{}`` spanning the
    whole expression is kept, as it denotes a set of acceptable answers (see
    :func:`create_expression_set`). Brackets must be closed with the same
    kind: for mismatched brackets (e.g. ``[x+y)``) a :class:`BracketNotationError`
    is raised, carrying the same rewrite as a best-effort guess (often still
    parseable, since a wrong-*kind* mismatch is fixed by the rewrite itself).
    """
    matched = has_matching_brackets(expr)
    guess = expr.replace("[", "(").replace("]", ")")
    if not (matched and is_multiple_answers_wrapper(guess)):
        guess = guess.replace("{", "(").replace("}", ")")
    if not matched:
        raise BracketNotationError(guess, original=expr)
    return guess


def _classify_pipes(expr: str) -> tuple[list[int], list[int], list[int]]:
    """Positions of the ``|`` that open, close, or could do either (``a|b``, ``)|(``), each ascending."""

    def grouping(char: str) -> bool:
        return char.isalnum() or char in GROUPING

    starts = [0] if expr.startswith("|") else []
    ends: list[int] = []
    ambiguous: list[int] = []
    for i in range(1, len(expr) - 1):
        if expr[i] != "|":
            continue
        if grouping(expr[i - 1]) and not grouping(expr[i + 1]):
            ends.append(i)
        elif grouping(expr[i + 1]) and not grouping(expr[i - 1]):
            starts.append(i)
        else:
            ambiguous.append(i)
    if expr.endswith("|"):
        ends.append(len(expr) - 1)
    return starts, ends, ambiguous


def _resolve_ambiguous(chars: list[str], starts: list[int], ends: list[int], ambiguous: list[int]) -> None:
    """Make each ambiguous ``|`` in ``chars`` open or close, from the nearest ``|`` before it.

    After a closing one it opens; after an opening one it closes; after another
    ambiguous one, a run of them alternates, starting with opening.
    """
    latest_start = latest_end = previous_ambiguous = -1
    next_start = next_end = 0  # indices into starts/ends, advanced as the scan moves right
    ambiguous_seen = 0
    for i in ambiguous:
        while next_start < len(starts) and starts[next_start] < i:
            latest_start = starts[next_start]
            next_start += 1
        while next_end < len(ends) and ends[next_end] < i:
            latest_end = ends[next_end]
            next_end += 1
        latest = max(latest_start, latest_end, previous_ambiguous)
        # chars[i - 1] may already be a replacement ("Abs(" or ")"), which is not alphanumeric
        opening = "*Abs(" if chars[i - 1].isalnum() else "Abs("
        if latest == latest_end:
            chars[i] = opening
        elif latest == previous_ambiguous:
            chars[i] = opening if ambiguous_seen % 2 == 0 else ")"
            ambiguous_seen += 1
        else:
            chars[i] = ")"
        previous_ambiguous = i


def convert_absolute_notation(expr: str, *, name: str | None = None) -> str:
    """Rewrite ``|x|`` as ``Abs(x)``.

    Nested ``|`` cannot be handled: each ``|`` is paired with the closest one
    to its right, and an :class:`AbsoluteValueNotationError` (naming ``name``,
    e.g. ``"response"``, if given) is raised, carrying the best guess, when
    that pairing was ambiguous or a ``|`` is left unpaired.
    """
    n_pipes = expr.count("|")
    if n_pipes == 0:
        return expr
    if n_pipes == 2:
        # Always one pair, whatever surrounds it: the general rules would make a|b|c "a*Abs(b*Abs(c".
        first = expr.index("|")
        second = expr.index("|", first + 1)
        return f"{expr[:first]}Abs({expr[first + 1 : second]}){expr[second + 1 :]}"
    starts, ends, ambiguous = _classify_pipes(expr)
    chars = list(expr)
    for i in starts:
        chars[i] = "Abs("
    for i in ends:  # after starts: a lone "|" is both, and becomes ")"
        chars[i] = ")"
    _resolve_ambiguous(chars, starts, ends, ambiguous)
    expr = "".join(chars)
    if ambiguous or n_pipes % 2:
        raise AbsoluteValueNotationError(expr, name=name)
    return expr


def preprocess_expression(expr: str, params: ExpressionParams, *, name: str | None = None) -> str:
    """Substitute symbol aliases and rewrite bracket and absolute-value notation.

    ``name`` (e.g. ``"response"``), if given, identifies what's being
    preprocessed in raised exceptions. Both bracket and absolute-value notation are always
    attempted, in sequence, and the resulting best-effort rewrite is always
    computed even when raising; a :class:`BracketNotationError` takes
    precedence over an :class:`AbsoluteValueNotationError` when both apply.
    """
    original = expr.strip()
    expr = substitute_input_symbols(original, params)
    bracket_error: BracketNotationError | None = None
    if not params.strict_syntax:
        try:
            expr = convert_bracket_notation(expr)
        except BracketNotationError as exc:
            expr = exc.expression
            bracket_error = exc
    try:
        expr = convert_absolute_notation(expr, name=name)
    except AbsoluteValueNotationError as exc:
        expr = exc.expression
        if bracket_error is None:
            raise
    if bracket_error is not None:
        raise BracketNotationError(expr, original=original)
    return expr
