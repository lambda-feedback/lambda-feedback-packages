"""Text substitution: replacing aliases with canonical names before parsing."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from .symbol_tables import ELEMENTARY_FUNCTIONS, GREEK_SYMBOLS, UNICODE_DASHES

if TYPE_CHECKING:
    from .params import ExpressionParams

# (original, replacement); an original of the form (text, lookaheads) only
# matches when followed by one of the lookahead strings.
Substitution = tuple[str | tuple[str, Sequence[str]], str]


def substitutions_sort_key(pair: tuple[str, str]) -> float:
    """Longer originals first; among equal ones, longer replacements first."""
    return -len(pair[0]) - len(pair[1]) / (10 ** (1 + len(str(len(pair[1])))))


def _sorted(substitutions: Sequence[tuple[str, str]]) -> list[tuple[str, str]]:
    # The pair itself breaks ties, so the order never depends on the hash seed.
    return sorted(set(substitutions), key=lambda pair: (substitutions_sort_key(pair), pair))


def substitute(string: str | Sequence[str | object], substitutions: Sequence[Substitution]) -> str:
    """Replace each occurrence of a substitution's original with its replacement.

    The input is scanned left to right; at each position the first matching
    substitution is applied and its replacement is not scanned again. So
    order only matters when originals overlap at the same position, where
    sorting with :func:`substitutions_sort_key` (longest first) is usually
    what you want. ``string`` may also be a list mixing strings (scanned) and
    other parts (kept as they are). Examples::

        substitute("abc bc c", [("abc", "p"), ("bc", "q"), ("c", "r")])  -> "p q r"
        substitute("p bc c", [("p", "abc"), ("bc", "q"), ("c", "r")])    -> "abc q r"
        substitute("sin(x) sinx", [(("sin", ["("]), "S")])               -> "S(x) sinx"
    """
    parts: Sequence[str | object] = [string] if isinstance(string, str) else string

    new_string: list[object] = []
    for part in parts:
        if not isinstance(part, str):
            new_string.append(part)
            continue
        index = 0
        buffer = ""
        while index < len(part):
            for k, (original, _) in enumerate(substitutions):
                if isinstance(original, tuple):
                    text, lookaheads = original
                    match = any(part.startswith(text + lookahead, index) for lookahead in lookaheads)
                    length = len(text)
                else:
                    match = part.startswith(original, index)
                    length = len(original)
                if match:
                    if buffer:
                        new_string.append(buffer)
                        buffer = ""
                    new_string.append(k)
                    index += length
                    break
            else:
                buffer += part[index]
                index += 1
        if buffer:
            new_string.append(buffer)

    return "".join(substitutions[elem][1] if isinstance(elem, int) else str(elem) for elem in new_string)


def greek_symbol_substitutions(expr: str) -> list[tuple[str, str]]:
    """Substitutions padding Greek names, and mapping Greek letters to names, found in ``expr``."""
    return _named_substitutions(GREEK_SYMBOLS, expr)


def elementary_function_substitutions(expr: str) -> list[tuple[str, str]]:
    """Substitutions padding function names, and mapping aliases to names, found in ``expr``."""
    return _named_substitutions(ELEMENTARY_FUNCTIONS, expr)


def _named_substitutions(table: Sequence[tuple[str, Sequence[str]]], expr: str) -> list[tuple[str, str]]:
    substitutions = []
    for name, aliases in table:
        if name in expr:
            substitutions.append((name, f" {name} "))
        substitutions += [(alias, f" {name} ") for alias in aliases if alias in expr]
    return substitutions


def unicode_dash_substitutions(expr: str) -> list[tuple[str, str]]:
    """Substitutions mapping the Unicode dashes found in ``expr`` to ``-``."""
    return [(dash, "-") for dash in UNICODE_DASHES if dash in expr]


def substitute_input_symbols(exprs: str | Sequence[str], params: ExpressionParams) -> list[str]:
    """Replace symbol aliases (and related spellings) with symbol codes.

    Covers the task's ``symbols`` and legacy ``input_symbols``, ``±``/``∓``
    text, and (with ``elementary_functions``) function and Greek aliases;
    ``lambda`` becomes ``lamda``, a Python keyword's usual stand-in (other
    keywords are handled when parsing). Longer originals take precedence.
    """
    exprs = [exprs] if isinstance(exprs, str) else list(exprs)

    substitutions: list[tuple[str, str]] = [(expr, expr) for expr in params.reserved_keywords]
    substitutions += [(expr, expr) for expr in params.unsplittable_symbols]
    if params.plus_minus is not None:
        substitutions.append((params.plus_minus, "plus_minus"))
    if params.minus_plus is not None:
        substitutions.append((params.minus_plus, "minus_plus"))

    symbol_aliases = {alias for spec in params.symbols.values() for alias in spec.aliases}
    if params.elementary_functions:
        for expr in exprs:
            for name, aliases in (*ELEMENTARY_FUNCTIONS, *GREEK_SYMBOLS):
                if name in symbol_aliases:
                    continue  # the task uses this name for one of its own symbols
                if name in expr:
                    substitutions.append((name, " " + name))
                substitutions += [
                    (alias, " " + name) for alias in aliases if alias in expr and alias not in symbol_aliases
                ]

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

    ordered = _sorted(substitutions)
    return [" ".join(substitute(expr, ordered).split()) for expr in exprs]
