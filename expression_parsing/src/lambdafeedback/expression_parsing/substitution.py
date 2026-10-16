"""Text substitution: replacing aliases with canonical names before parsing."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ._scanning import Match, replace_matches
from .symbol_tables import (
    ALWAYS_FUNCTIONS,
    ELEMENTARY_FUNCTIONS,
    EMBEDDABLE_FUNCTION_NAMES,
    GREEK_SYMBOLS,
    MINUS_PLUS,
    PLUS_MINUS,
    SUPERSCRIPTS,
    UNICODE_OPERATORS,
)

if TYPE_CHECKING:
    from .params import ExpressionParams


@dataclass(frozen=True)
class FunctionName:
    """An original that only matches when applied: followed (after any spaces) by ``(``, ``^`` or ``**``.

    So ``re(z)``, ``xre(z)`` and ``re^2(z)`` match but ``area`` doesn't. A
    whole-word test would not be reliable: each substitution pass pads the
    names it replaces (``interval`` becomes ``int Erval``), so a later pass
    would see word boundaries the learner never wrote.
    """

    text: str

    def matches(self, string: str, index: int) -> bool:
        if not string.startswith(self.text, index):
            return False
        end = index + len(self.text)
        while end < len(string) and string[end] == " ":  # not string[end:].lstrip(): that copies the rest
            end += 1
        return string.startswith(("(", "^", "**"), end)


Substitution = tuple[str | FunctionName, str]
"""``(original, replacement)``; a :class:`FunctionName` original only matches where it is applied."""


def _original_text(original: str | FunctionName) -> str:
    return original.text if isinstance(original, FunctionName) else original


def substitutions_sort_key(pair: Substitution) -> tuple[int, int]:
    """Longer originals first; among equal ones, longer replacements first."""
    return -len(_original_text(pair[0])), -len(pair[1])


def sorted_substitutions(substitutions: Sequence[Substitution]) -> list[Substitution]:
    """De-duplicated and sorted by :func:`substitutions_sort_key`.

    Ties are broken by content, so the order never depends on the hash seed.
    """

    def key(pair: Substitution) -> tuple[int, int, str, bool, str]:
        return (*substitutions_sort_key(pair), _original_text(pair[0]), isinstance(pair[0], FunctionName), pair[1])

    return sorted(set(substitutions), key=key)


def substitute(string: str, substitutions: Sequence[Substitution]) -> str:
    """Replace each occurrence of a substitution's original with its replacement.

    The input is scanned left to right; at each position the first matching
    substitution is applied and its replacement is not scanned again. So
    order only matters when originals overlap at the same position, where
    sorting with :func:`sorted_substitutions` (longest first) is usually
    what you want. Examples::

        substitute("abc bc c", [("abc", "p"), ("bc", "q"), ("c", "r")])  -> "p q r"
        substitute("p bc c", [("p", "abc"), ("bc", "q"), ("c", "r")])    -> "abc q r"
        substitute("sin(x) sinx", [(FunctionName("sin"), "S")])          -> "S(x) sinx"
    """
    # Only substitutions whose original starts with the character at hand can match there:
    # trying all of them at every position made long inputs slow (length x substitutions).
    # Each list keeps the substitutions' order, so the first match is the same.
    by_first: dict[str, list[tuple[int, Substitution]]] = {}
    always: list[tuple[int, Substitution]] = []  # empty originals
    for k, substitution in enumerate(substitutions):
        text = _original_text(substitution[0])
        if text:
            by_first.setdefault(text[0], []).append((k, substitution))
        else:
            always.append((k, substitution))
    if always:
        for first, candidates in by_first.items():
            by_first[first] = sorted([*candidates, *always], key=lambda candidate: candidate[0])

    pieces: list[str] = []
    done = index = 0
    while index < len(string):
        for _, (original, replacement) in by_first.get(string[index], always):
            if isinstance(original, FunctionName):
                match = original.matches(string, index)
                length = len(original.text)
            else:
                match = string.startswith(original, index)
                length = len(original)
            if match:
                pieces += [string[done:index], replacement]
                index = done = index + length
                break
        else:
            index += 1
    pieces.append(string[done:])
    return "".join(pieces)


def greek_symbol_substitutions(expr: str) -> list[Substitution]:
    """Substitutions padding Greek names, and mapping Greek letters to names, found in ``expr``."""
    return _named_substitutions(GREEK_SYMBOLS, expr, " {} ")


def elementary_function_substitutions(expr: str) -> list[Substitution]:
    """Substitutions padding function names, and mapping aliases to names, found in ``expr``.

    Names that are common inside ordinary words (``re`` in ``area``, ``int``
    in ``interval``; see :data:`EMBEDDABLE_FUNCTION_NAMES`) only count where
    they read as a function (see :class:`FunctionName`).
    """
    return _named_substitutions(ELEMENTARY_FUNCTIONS, expr, " {} ")


def _function_original(text: str) -> str | FunctionName:
    return FunctionName(text) if text.casefold() in EMBEDDABLE_FUNCTION_NAMES else text


def _always_function_original(text: str, symbol_aliases: set[str]) -> str | FunctionName:
    """An :data:`ALWAYS_FUNCTIONS` spelling; one the task also uses as an alias only matches where applied."""
    if text in symbol_aliases:
        return FunctionName(text)
    return _function_original(text)


def _named_substitutions(table: Sequence[tuple[str, Sequence[str]]], expr: str, padding: str) -> list[Substitution]:
    """``(spelling, padded name)`` for each name and alias in ``table`` found in ``expr``."""
    replacement = padding.format
    return [
        (_function_original(spelling), replacement(name))
        for name, aliases in table
        for spelling in (name, *aliases)
        if spelling in expr
    ]


_UNICODE_OPERATOR_TABLE = str.maketrans(dict(UNICODE_OPERATORS))


def normalise_unicode_operators(expr: str) -> str:
    """Write Unicode operators in ASCII: ``−`` → ``-``, ``×``/``·`` → ``*``, ``÷`` → ``/``, ``x²`` → ``x**(2)``.

    Only operators with one unambiguous meaning (see
    :data:`UNICODE_OPERATORS` and :data:`SUPERSCRIPTS`); others, such as
    ``√`` or ``½``, are left for parsing to report.
    """
    return replace_matches(expr.translate(_UNICODE_OPERATOR_TABLE), _superscript_run)


def _superscript_run(expr: str, index: int) -> Match | None:
    """Finder for :func:`replace_matches`: the first run of superscripts at or after ``index``, as a power."""
    start = next((k for k in range(index, len(expr)) if expr[k] in SUPERSCRIPTS), None)
    if start is None:
        return None
    end = start
    while end < len(expr) and expr[end] in SUPERSCRIPTS:
        end += 1
    # The power replaces any spaces before the run, and a redundant ^ or ** before those (x^²).
    before = expr[index:start].rstrip(" ")
    before = before.removesuffix("^") if before.endswith("^") else before.removesuffix("**")
    return index + len(before), end, "**(" + "".join(SUPERSCRIPTS[char] for char in expr[start:end]) + ")"


def substitute_input_symbols(expr: str, params: ExpressionParams) -> str:
    """Replace symbol aliases (and related spellings) with symbol codes.

    Covers the task's ``symbols`` and legacy ``input_symbols``, ``±``/``∓``
    text, and (with ``elementary_functions``) function and Greek aliases;
    ``lambda`` becomes ``lamda``, a Python keyword's usual stand-in (other
    keywords are handled when parsing). Longer originals take precedence.
    Unicode operators are written in ASCII first (see
    :func:`normalise_unicode_operators`).
    """
    expr = normalise_unicode_operators(expr)

    substitutions: list[Substitution] = [(name, name) for name in params.reserved_keywords]
    substitutions += [(name, name) for name in params.unsplittable_symbols]
    if params.plus_minus is not None:
        substitutions.append((params.plus_minus, PLUS_MINUS))
    if params.minus_plus is not None:
        substitutions.append((params.minus_plus, MINUS_PLUS))

    symbol_aliases = {alias for spec in params.symbols.values() for alias in spec.aliases}
    if params.elementary_functions:
        for table, original in ((ELEMENTARY_FUNCTIONS, _function_original), (GREEK_SYMBOLS, str)):
            for name, aliases in table:
                spellings = [spelling for spelling in (name, *aliases) if spelling in expr]
                if name in ALWAYS_FUNCTIONS:
                    # Applied, still the function; on its own, the task's symbol.
                    substitutions += [
                        (_always_function_original(spelling, symbol_aliases), " " + name) for spelling in spellings
                    ]
                    continue
                if name in symbol_aliases:
                    continue  # the task uses this name for one of its own symbols
                spellings = [spelling for spelling in spellings if spelling not in symbol_aliases]
                substitutions += [(original(spelling), " " + name) for spelling in spellings]

    for code, spec in params.symbols.items():
        substitutions.append((code, code))
        substitutions += [(alias, code) for alias in spec.aliases]

    # Legacy [code, [alternatives]] symbol definitions
    for code, alternatives in params.input_symbols:
        substitutions.append((code, code))
        substitutions += [(alternative, code) for alternative in alternatives]

    # 'lambda' is a Python keyword: never substitute it back in. Only the whole
    # name: longer names such as 'lambda_1' are valid identifiers and must
    # match their codes in params.symbols.
    substitutions = [
        (original, "lamda" if replacement == "lambda" else replacement) for original, replacement in substitutions
    ]

    return " ".join(substitute(expr, sorted_substitutions(substitutions)).split())
