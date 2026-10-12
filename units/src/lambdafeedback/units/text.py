"""Cleaning up a quantity response's text before it is parsed (whitespace, product signs, LaTeX), and checks on it."""

from __future__ import annotations

from functools import cache
from string import ascii_letters

from lambdafeedback.expression_parsing import UNICODE_OPERATORS

from .data import ALL_UNITS, SI_PREFIXES, AnyUnit, units_in

# Product signs as in expression parsing (·, ⋅, ∙, ×), and zero-width characters dropped.
PRODUCT_SIGNS = str.maketrans(
    {
        **{sign: "*" for sign, ascii_sign in UNICODE_OPERATORS.items() if ascii_sign == "*"},
        **dict.fromkeys("\u200b\u200c\u200d\ufeff"),
    }
)
_LETTERS = frozenset(ascii_letters)
_UPRIGHT_COMMANDS = ("mathrm", "text", "textrm", "operatorname")


def _is_word_character(char: str) -> bool:
    return char.isalnum() or char == "_"


def called_names(expr: str) -> list[str]:
    """The names followed by ``(`` (function calls) in ``expr``; a name starts with an ASCII letter or ``_``."""
    names = []
    bracket = expr.find("(")
    while bracket != -1:
        end = bracket
        while end > 0 and expr[end - 1].isspace():
            end -= 1
        start = end
        while start > 0 and _is_word_character(expr[start - 1]):
            start -= 1
        while start < end and not (expr[start] in ascii_letters or expr[start] == "_"):
            start += 1
        if start < end:
            names.append(expr[start:end])
        bracket = expr.find("(", bracket + 1)
    return names


def collapse_whitespace(text: str) -> str:
    """Each run of whitespace in ``text`` as one space (including at either end)."""
    collapsed = " ".join(text.split())
    if text[:1].isspace():
        collapsed = " " + collapsed
    if text[-1:].isspace() and collapsed != " ":
        collapsed += " "
    return collapsed


def mentions_celsius_or_fahrenheit(expr: str) -> bool:
    """Whether ``expr`` has ``℃``, ``℉``, or ``°``/``deg``/``degree``/``degrees`` then ``C`` or ``F``.

    Read as degree times coulomb (or farad) otherwise.
    """
    if "℃" in expr or "℉" in expr:
        return True

    def celsius_or_fahrenheit_at(index: int) -> bool:
        while index < len(expr) and expr[index].isspace():
            index += 1
        return expr[index : index + 1] in ("C", "F") and expr[index + 1 : index + 2] not in _LETTERS

    for index, char in enumerate(expr):
        if char == "°" and celsius_or_fahrenheit_at(index + 1):
            return True
        if (
            expr.startswith("deg", index)
            and (index == 0 or expr[index - 1] not in ascii_letters)
            and any(
                expr.startswith(suffix, index + 3) and celsius_or_fahrenheit_at(index + 3 + len(suffix))
                for suffix in ("rees", "ree", "")
            )
        ):
            return True
    return False


@cache
def _unselected_unit_forms(unit_sets: frozenset[str]) -> dict[str, AnyUnit]:
    """Spellings (names, alternatives, plurals, with or without a prefix name) of units outside ``unit_sets``.

    Symbols are left out: a letter such as ``h`` or ``L`` in a value is more
    likely a variable than an hour or a litre. A spelling of a selected unit is
    never included.
    """
    prefixes = ("", *(prefix.name for prefix in SI_PREFIXES))

    def spellings(unit: AnyUnit) -> set[str]:
        return {prefix + form for form in (unit.name, *unit.alternatives, *unit.plurals) for prefix in prefixes}

    selected = units_in(unit_sets)
    allowed = set().union(*map(spellings, selected))
    forms: dict[str, AnyUnit] = {}
    for unit in ALL_UNITS:
        if unit not in selected:
            for form in spellings(unit) - allowed:
                forms.setdefault(form, unit)
    return forms


def disallowed_unit(text: str, unit_sets: frozenset[str]) -> tuple[str, AnyUnit] | None:
    """The first whole word of ``text`` (and its unit) that spells a unit outside ``unit_sets``, if any.

    A word is a run of letters and ``_``; one after ``\\`` is a LaTeX command.
    Characters that aren't letters (``°``) are checked one at a time.
    """
    forms = _unselected_unit_forms(unit_sets)
    index = 0
    while index < len(text):
        start = index
        if text[index].isalpha() or text[index] == "_":
            while index < len(text) and (text[index].isalpha() or text[index] == "_"):
                index += 1
            if start > 0 and text[start - 1] == "\\":
                continue
        else:
            index += 1
        unit = forms.get(text[start:index])
        if unit is not None:
            return text[start:index], unit
    return None


def normalise_latex(expr: str) -> str:
    """LaTeX spacing (``~``, ``\\,``) as spaces and upright text (``\\mathrm{m}``) as plain text.

    MathLive writes ``2~\\mathrm{m}``; the quantity grammar needs ``2 m``.
    """
    spaced = []
    index = 0
    while index < len(expr):
        if expr[index] == "~":
            spaced.append(" ")
            index += 1
        elif expr.startswith("\\", index) and expr[index + 1 : index + 2] in (",", ";", ":", " "):
            spaced.append(" ")
            index += 2
        elif quad := next((q for q in ("\\qquad", "\\quad") if expr.startswith(q, index)), None):
            after = index + len(quad)
            if after < len(expr) and _is_word_character(expr[after]):
                spaced.append(expr[index])
                index += 1
            else:
                spaced.append(" ")
                index = after
        else:
            spaced.append(expr[index])
            index += 1
    return _unwrap_upright("".join(spaced))


def _unwrap_upright(expr: str) -> str:
    """``\\mathrm{m}``, ``\\text{m}``, ... as ``m`` (when the braces hold no other braces).

    Unlike ``expression_parsing.sanitise_latex`` this also unwraps ``\\textrm``
    and ``\\operatorname``, leaves nested braces alone and never raises: a unit
    preview should degrade, not fail.
    """
    unwrapped = []
    index = 0
    while (backslash := expr.find("\\", index)) != -1:
        unwrapped.append(expr[index:backslash])
        index = backslash + 1
        for command in _UPRIGHT_COMMANDS:
            start = backslash + 1 + len(command) + 1
            if not expr.startswith(command + "{", backslash + 1):
                continue
            end = expr.find("}", start)
            if end != -1 and "{" not in expr[start:end]:
                unwrapped.append(expr[start:end])
                index = end + 1
                break
        else:
            unwrapped.append("\\")
    unwrapped.append(expr[index:])
    return "".join(unwrapped)


def normalise_input(expr: str, *, latex: bool) -> str:
    """``expr`` with product signs as ``*``, zero-width characters dropped and whitespace collapsed.

    With ``latex``, LaTeX spacing and upright text are read as plain spaces and text too (see :func:`normalise_latex`).
    """
    text = collapse_whitespace(expr.translate(PRODUCT_SIGNS))
    return normalise_latex(text) if latex else text
