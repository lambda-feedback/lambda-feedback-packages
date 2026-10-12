"""Names recognised in expressions: elementary functions and Greek letters, with aliases."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import NamedTuple

PLUS_MINUS = "plus_minus"
"""The name ``±`` is written as before it is expanded into both signs."""
MINUS_PLUS = "minus_plus"
"""The name ``∓`` is written as before it is expanded into both signs."""


class SymbolAliases(NamedTuple):
    """A canonical name and the other ways of writing it."""

    name: str
    aliases: tuple[str, ...]


def _with_upper_case(entries: list[tuple[str, list[str]]]) -> tuple[SymbolAliases, ...]:
    """Add the upper-case form of each name and alias (e.g. ``SIN`` for ``sin``)."""
    result = []
    for name, aliases in entries:
        upper = [name.upper()]
        for alias in aliases:
            if alias.upper() not in upper:
                upper.append(alias.upper())
        result.append(SymbolAliases(name, (*aliases, *upper)))
    return tuple(result)


ELEMENTARY_FUNCTIONS = _with_upper_case(
    [
        ("sin", []), ("sinc", []), ("csc", ["cosec"]), ("cos", []), ("sec", []), ("tan", []), ("cot", ["cotan"]),
        ("asin", ["arcsin"]), ("acsc", ["arccsc", "arccosec", "acosec"]), ("acos", ["arccos"]), ("asec", ["arcsec"]),
        ("atan", ["arctan"]), ("acot", ["arccot", "arccotan", "acotan"]), ("atan2", ["arctan2"]),
        ("sinh", []), ("cosh", []), ("tanh", []), ("csch", ["cosech"]), ("sech", []),
        ("asinh", ["arcsinh"]), ("acosh", ["arccosh"]), ("atanh", ["arctanh"]),
        ("acsch", ["arccsch", "arccosech"]), ("asech", ["arcsech"]),
        ("exp", ["Exp"]), ("E", ["e"]), ("log", ["ln"]),
        ("sqrt", []), ("sign", []), ("Abs", ["abs"]), ("Max", ["max"]), ("Min", ["min"]), ("arg", []),
        ("ceiling", ["ceil"]), ("floor", []),
        ("oo", ["Infinity", "inf", "infinity", "∞"]),
        # Kept intact during preprocessing so that ± / ∓ expansion still works
        (PLUS_MINUS, []), (MINUS_PLUS, []),
        # Common operations rather than elementary functions, but handled the same way
        ("summation", ["sum", "Sum"]), ("Integral", ["int"]), ("Derivative", ["diff"]), ("re", ["real"]),
        ("im", ["imag"]), ("conjugate", ["conj"]),
    ]
)  # fmt: skip
"""Function (and constant) names with their aliases, used when ``elementary_functions`` is enabled."""

EMBEDDABLE_FUNCTION_NAMES = frozenset({"re", "im", "int", "arg", "sum", "sign", "min", "max", "sec"})
"""Function spellings common inside ordinary words (``area``, ``time``, ``interval``, ``design``).

They only count as a function when followed by ``(``, ``^`` or ``**``
(compared case-insensitively, so ``RE`` and ``Max`` too); anywhere else,
including on their own, they are read as letters.
"""

GREEK_SYMBOLS: tuple[SymbolAliases, ...] = tuple(
    SymbolAliases(name, tuple(aliases))
    for name, aliases in [
        ("Alpha", ["Α", "𝚨", "𝛢", "𝜜", "𝝖", "𝞐"]),
        ("alpha", ["α", "𝛂", "𝛼", "𝜶", "𝝰", "𝞪"]),
        ("Beta", ["Β", "𝚩", "𝛣", "𝜝", "𝝗", "𝞑"]),
        ("beta", ["β", "ϐ", "𝛃", "𝛽", "𝜷", "𝝱", "𝞫"]),
        ("Gamma", ["Γ", "𝚪", "𝛤", "𝜞", "𝝘", "𝞒"]),
        ("gamma", ["γ", "𝛄", "𝛾", "𝜸", "𝝲", "𝞬"]),
        ("Delta", ["Δ", "𝚫", "𝛥", "𝜟", "𝝙", "𝞓"]),
        ("delta", ["δ", "𝛅", "𝛿", "𝜹", "𝝳", "𝞭"]),
        ("Epsilon", ["Ε", "𝚬", "𝛦", "𝜠", "𝝚", "𝞔"]),
        ("epsilon", ["ε", "ϵ", "𝛆", "𝜀", "𝜺", "𝝴", "𝞊", "𝞮"]),
        ("Zeta", ["Ζ", "𝚭", "𝛧", "𝜡", "𝝛", "𝞕"]),
        ("zeta", ["ζ", "𝛇", "𝜁", "𝜻", "𝝵", "𝞯"]),
        ("Eta", ["Η", "𝚮", "𝛨", "𝜢", "𝝜", "𝞖"]),
        ("eta", ["η", "𝛈", "𝜂", "𝜼", "𝝶", "𝞰"]),
        ("Theta", ["Θ", "ϴ", "𝚯", "𝛩", "𝜣", "𝝝", "𝞗"]),
        ("theta", ["θ", "ϑ", "𝛉", "𝜃", "𝜗", "𝜽", "𝝑", "𝝷", "𝞋", "𝞱"]),
        ("Iota", ["Ι", "𝚰", "𝛪", "𝜤", "𝝞", "𝞘"]),
        ("iota", ["ι", "𝛊", "𝜄", "𝜾", "𝝸", "𝞲"]),
        ("Kappa", ["Κ", "𝚱", "𝛫", "𝜥", "𝝟", "𝞙"]),
        ("kappa", ["κ", "ϰ", "𝛋", "𝜅", "𝜘", "𝜿", "𝝒", "𝝹", "𝞌", "𝞳"]),
        ("Lambda", ["Λ", "𝚲", "𝛬", "𝜦", "𝝠", "𝞚"]),
        ("lamda", ["λ", "𝛌", "𝜆", "𝝀", "𝝺", "𝞴"]),  # "lambda" is a Python keyword
        ("Mu", ["Μ", "𝚳", "𝛭", "𝜧", "𝝡", "𝞛"]),
        ("mu", ["μ", "µ", "𝛍", "𝜇", "𝝁", "𝝻", "𝞵"]),
        ("Nu", ["Ν", "𝚴", "𝛮", "𝜨", "𝝢", "𝞜"]),
        ("nu", ["ν", "𝛎", "𝜈", "𝝂", "𝝼", "𝞶"]),
        ("Xi", ["Ξ", "𝚵", "𝛯", "𝜩", "𝝣", "𝞝"]),
        ("xi", ["ξ", "𝛏", "𝜉", "𝝃", "𝝽", "𝞷"]),
        ("Omicron", ["Ο", "𝚶", "𝛰", "𝜪", "𝝤", "𝞞"]),
        ("omicron", ["ο", "𝛐", "𝜊", "𝝄", "𝝾", "𝞸"]),
        ("Pi", ["Π", "𝚷", "𝛱", "𝜫", "𝝥", "𝞟"]),
        ("pi", ["π", "ϖ", "𝛑", "𝜋", "𝝅", "𝝿", "𝞹"]),
        ("Rho", ["Ρ", "𝚸", "𝛲", "𝜬", "𝝦", "𝞠"]),
        ("rho", ["ρ", "ϱ", "𝛒", "𝜌", "𝝆", "𝞀", "𝞺"]),
        ("Sigma", ["Σ", "𝚺", "𝛴", "𝜮", "𝝨", "𝞢"]),
        ("sigma", ["σ", "ς", "𝛔", "𝜎", "𝝈", "𝞂", "𝞼"]),
        ("Tau", ["Τ", "𝚻", "𝛵", "𝜯", "𝝩", "𝞣"]),
        ("tau", ["τ", "𝛕", "𝜏", "𝝉", "𝞃", "𝞽"]),
        ("Upsilon", ["Υ", "𝚼", "𝛶", "𝜰", "𝝪", "𝞤"]),
        ("upsilon", ["υ", "𝛖", "𝜐", "𝝊", "𝞄", "𝞾"]),
        ("Phi", ["Φ", "𝚽", "𝛷", "𝜱", "𝝫", "𝞥"]),
        ("phi", ["φ", "ϕ", "𝛗", "𝜑", "𝜙", "𝝋", "𝝓", "𝞅", "𝞍", "𝞿", "𝟇"]),
        ("Chi", ["Χ", "𝚾", "𝛸", "𝜲", "𝝬", "𝞦"]),
        ("chi", ["χ", "𝛘", "𝜒", "𝝌", "𝞆", "𝟀"]),
        ("Psi", ["Ψ", "𝚿", "𝛹", "𝜳", "𝝭", "𝞧"]),
        ("psi", ["ψ", "𝛙", "𝜓", "𝝍", "𝞇", "𝟁"]),
        ("Omega", ["Ω", "𝛀", "𝛺", "𝜴", "𝝮", "𝞨"]),
        ("omega", ["ω", "𝛚", "𝜔", "𝝎", "𝞈", "𝟂"]),
    ]
)
"""Greek letter names with their Unicode (and mathematical alphanumeric) forms."""

UNICODE_DASHES = (
    "‐",  # HYPHEN
    "‑",  # NON-BREAKING HYPHEN
    "‒",  # FIGURE DASH
    "–",  # EN DASH
    "—",  # EM DASH
    "−",  # MINUS SIGN
    "﹣",  # SMALL HYPHEN-MINUS
    "－",  # FULLWIDTH HYPHEN-MINUS
)

UNICODE_OPERATORS: Mapping[str, str] = MappingProxyType(
    {
        **dict.fromkeys(UNICODE_DASHES, "-"),
        "×": "*",  # MULTIPLICATION SIGN
        "·": "*",  # MIDDLE DOT
        "⋅": "*",  # DOT OPERATOR
        "∙": "*",  # BULLET OPERATOR
        "÷": "/",  # DIVISION SIGN
        "∕": "/",  # DIVISION SLASH
    }
)
"""Unicode operators (as typed on phones or pasted from documents) and their ASCII forms."""

SUPERSCRIPTS: Mapping[str, str] = MappingProxyType({
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
    "⁻": "-", "⁺": "+",
})  # fmt: skip
"""Superscript characters; a run of them is an exponent (``x²`` is ``x**(2)``)."""
