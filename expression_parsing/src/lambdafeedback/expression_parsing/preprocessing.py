"""String-level preprocessing of responses before they are parsed."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from .errors import AbsoluteValueNotationError, BracketNotationError
from .substitution import substitute_input_symbols

if TYPE_CHECKING:
    from .params import ExpressionParams

_BRACKET_PAIRS = {")": "(", "]": "[", "}": "{"}
_GROUPING = "()[]{}"


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


def has_matching_brackets(expr: str) -> bool:
    """True if every ``(``, ``[``, ``{`` is closed by the same kind, correctly nested.

    Mismatched kinds (e.g. the ``[x+y)`` of interval notation) and unbalanced
    brackets are rejected.
    """
    stack = []
    for char in expr:
        if char in "([{":
            stack.append(char)
        elif char in ")]}" and (not stack or stack.pop() != _BRACKET_PAIRS[char]):
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
        expr = substitute_input_symbols(original, params)[0]
        if params.plus_minus is not None:
            expr = expr.replace(params.plus_minus, "plus_minus")
        if params.minus_plus is not None:
            expr = expr.replace(params.minus_plus, "minus_plus")
        expanded.update(dict.fromkeys(_expand_plus_minus(expr)))
    return list(expanded)


def _expand_plus_minus(expr: str) -> list[str]:
    """Both signs of an expression containing ``plus_minus``/``minus_plus`` (otherwise just ``expr``)."""
    if "plus_minus" not in expr and "minus_plus" not in expr:
        return [expr]
    signed = (
        expr.replace("plus_minus", plus_minus).replace("minus_plus", minus_plus).strip()
        for plus_minus, minus_plus in (("+", "-"), ("-", "+"))
    )
    return [s.lstrip("+").strip() for s in signed]


def _split_top_level(text: str) -> list[str]:
    """Split ``text`` at the commas that aren't inside brackets."""
    parts = []
    depth = start = 0
    for index, char in enumerate(text):
        if char in "([{":
            depth += 1
        elif char in ")]}":
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


def convert_absolute_notation(expr: str, name: str) -> str:
    """Rewrite ``|x|`` as ``Abs(x)``.

    Nested ``|`` cannot be handled: each ``|`` is paired with the closest one
    to its right, and an :class:`AbsoluteValueNotationError` (naming ``name``,
    e.g. ``"response"``) is raised, carrying the best guess, when that
    pairing was ambiguous or a ``|`` is left unpaired.
    """
    n_pipes = expr.count("|")
    ambiguous: list[int] = []
    if n_pipes == 2:
        chars = list(expr)
        chars[chars.index("|")] = "Abs("
        chars[chars.index("|")] = ")"
        expr = "".join(chars)
    elif n_pipes > 0:
        starts: list[int] = []
        ends: list[int] = []

        def grouping(char: str) -> bool:
            return char.isalnum() or char in _GROUPING

        if expr[0] == "|":
            starts.append(0)
        for i in range(1, len(expr) - 1):
            if expr[i] == "|":
                if grouping(expr[i - 1]) and not grouping(expr[i + 1]):
                    ends.append(i)
                elif grouping(expr[i + 1]) and not grouping(expr[i - 1]):
                    starts.append(i)
                else:
                    ambiguous.append(i)
        if expr[-1] == "|":
            ends.append(len(expr) - 1)
        chars = list(expr)
        for i in starts:
            chars[i] = "Abs("
        for i in ends:
            chars[i] = ")"
        k = 0
        previous_ambiguous = -1
        for i in ambiguous:
            previous_start = max((j for j in starts if j < i), default=-1)
            previous_end = max((j for j in ends if j < i), default=-1)
            latest = max(previous_start, previous_end, previous_ambiguous)
            # chars[i - 1] may already be a replacement ("Abs(" or ")"), which is not alphanumeric
            opening = "*Abs(" if chars[i - 1].isalnum() else "Abs("
            if latest == previous_end:
                chars[i] = opening
            elif latest == previous_ambiguous:
                chars[i] = opening if k % 2 == 0 else ")"
                k += 1
            else:
                chars[i] = ")"
            previous_ambiguous = i
        expr = "".join(chars)

    if (n_pipes > 2 and ambiguous) or n_pipes % 2:
        raise AbsoluteValueNotationError(expr, name)
    return expr


def preprocess_expression(name: str, expr: str, params: ExpressionParams) -> str:
    """Substitute symbol aliases and rewrite bracket and absolute-value notation.

    ``name`` (e.g. ``"response"``) identifies what's being preprocessed in
    raised exceptions. Both bracket and absolute-value notation are always
    attempted, in sequence, and the resulting best-effort rewrite is always
    computed even when raising; a :class:`BracketNotationError` takes
    precedence over an :class:`AbsoluteValueNotationError` when both apply.
    """
    original = expr.strip()
    expr = substitute_input_symbols(original, params)[0]
    bracket_error: BracketNotationError | None = None
    if not params.strict_syntax:
        try:
            expr = convert_bracket_notation(expr)
        except BracketNotationError as exc:
            expr = exc.expression
            bracket_error = exc
    try:
        expr = convert_absolute_notation(expr, name)
    except AbsoluteValueNotationError as exc:
        expr = exc.expression
        if bracket_error is None:
            raise
    if bracket_error is not None:
        raise BracketNotationError(expr, original=original)
    return expr
