"""Text substitution: replacing aliases with canonical names before parsing."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .symbol_tables import ELEMENTARY_FUNCTIONS, EMBEDDABLE_FUNCTION_NAMES, GREEK_SYMBOLS, UNICODE_DASHES

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
        end = index + len(self.text)
        return string.startswith(self.text, index) and string[end:].lstrip(" ").startswith(("(", "^", "**"))


# (original, replacement); an original of the form (text, lookaheads) only
# matches when followed by one of the lookahead strings.
Substitution = tuple[str | tuple[str, Sequence[str]] | FunctionName, str]


def _original_text(original: str | tuple[str, Sequence[str]] | FunctionName) -> str:
    if isinstance(original, FunctionName):
        return original.text
    return original if isinstance(original, str) else original[0]


def substitutions_sort_key(pair: Substitution) -> float:
    """Longer originals first; among equal ones, longer replacements first."""
    return -len(_original_text(pair[0])) - len(pair[1]) / (10 ** (1 + len(str(len(pair[1])))))


def _sorted(substitutions: Sequence[Substitution]) -> list[Substitution]:
    # Ties are broken by content, so the order never depends on the hash seed.
    def key(pair: Substitution) -> tuple[float, str, bool, str]:
        return (substitutions_sort_key(pair), _original_text(pair[0]), not isinstance(pair[0], str), pair[1])

    return sorted(set(substitutions), key=key)


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
                if isinstance(original, FunctionName):
                    match = original.matches(part, index)
                    length = len(original.text)
                elif isinstance(original, tuple):
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


def _named_substitutions(table: Sequence[tuple[str, Sequence[str]]], expr: str, padding: str) -> list[Substitution]:
    """``(spelling, padded name)`` for each name and alias in ``table`` found in ``expr``."""
    replacement = padding.format
    return [
        (_function_original(spelling), replacement(name))
        for name, aliases in table
        for spelling in (name, *aliases)
        if spelling in expr
    ]


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

    substitutions: list[Substitution] = [(expr, expr) for expr in params.reserved_keywords]
    substitutions += [(expr, expr) for expr in params.unsplittable_symbols]
    if params.plus_minus is not None:
        substitutions.append((params.plus_minus, "plus_minus"))
    if params.minus_plus is not None:
        substitutions.append((params.minus_plus, "minus_plus"))

    symbol_aliases = {alias for spec in params.symbols.values() for alias in spec.aliases}
    if params.elementary_functions:
        for expr in exprs:
            for table, original in ((ELEMENTARY_FUNCTIONS, _function_original), (GREEK_SYMBOLS, str)):
                for name, aliases in table:
                    if name in symbol_aliases:
                        continue  # the task uses this name for one of its own symbols
                    spellings = [name] if name in expr else []
                    spellings += [alias for alias in aliases if alias in expr and alias not in symbol_aliases]
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

    ordered = _sorted(substitutions)
    return [" ".join(substitute(expr, ordered).split()) for expr in exprs]
