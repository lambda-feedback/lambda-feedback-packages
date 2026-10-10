"""Rewriting quantity responses before parsing."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from functools import cache
from itertools import groupby
from string import ascii_letters

from .data import ALL_UNITS, SI_PREFIXES
from .params import QuantityParams
from .quantity import MAX_INPUT_LENGTH

MAX_LEGACY_LENGTH = 1_000
"""Longest input the legacy rewrites are applied to, in characters.

They take time cubic in the length on some input (``"μ " * 500``, 1000
characters, needs about 125000 rewrites, each moving a space one step left):
about 0.4 s at this length, hours at 10000.
"""


def preprocess_quantity(name: str, expr: str, params: QuantityParams) -> str:
    """Normalise prefix spellings (or apply the legacy rewrites); never raises.

    Same shape as ``expression_parsing.preprocess_expression``, so either can
    serve as a context's preprocessing step. ``name`` is unused.

    Input longer than :data:`~lambdafeedback.units.MAX_INPUT_LENGTH` is
    returned unchanged (:func:`~lambdafeedback.units.parse_quantity` rejects
    it), and so is input longer than :data:`MAX_LEGACY_LENGTH` with legacy
    preprocessing.
    """
    if len(expr) > MAX_INPUT_LENGTH:
        return expr
    if params.legacy_preprocessing:
        return preprocess_legacy(expr) if len(expr) <= MAX_LEGACY_LENGTH else expr
    return transform_prefixes_to_standard(expr)


Span = tuple[int, int]
"""Where a match starts and ends in a string."""
Search = Callable[[str, int], Span | None]
"""``search(expr, position)``: the first match in ``expr`` starting at or after ``position``."""


def _rewrite_all(search: Search, expr: str, rewrite: Callable[[str, Span], str]) -> str:
    """Apply ``rewrite`` at the first match of ``search`` until nothing matches.

    Text before a rewrite is unchanged and held no match, so the next search
    starts just far enough back to catch a match reaching into the rewritten
    part. Starting from the beginning each time was cubic on long input.
    """
    position = 0
    while (span := search(expr, position)) is not None:
        expr = rewrite(expr, span)
        position = max(0, span[0] - _longest_match())
    return expr


@cache
def _longest_match() -> int:
    """At least as long as any match of the ``_rewrite_all`` searches.

    The longest is a prefix, a space and a unit form, plus a few marks.
    """
    forms = [form for prefix in SI_PREFIXES for form in (prefix.name, prefix.symbol, *prefix.alternatives)]
    forms += [form for unit in ALL_UNITS for form in (unit.name, unit.symbol, *unit.alternatives, *unit.plurals)]
    return 2 * max(map(len, forms)) + 8


class _Forms:
    """Unit or prefix spellings, found in the order given (the first that fits wins, as in a regex alternation)."""

    def __init__(self, forms: Iterable[str]) -> None:
        self._by_first_character: dict[str, list[str]] = {}
        for form in dict.fromkeys(forms):
            self._by_first_character.setdefault(form[0], []).append(form)

    def candidates(self, expr: str, index: int) -> list[str]:
        """The forms that could occur in ``expr`` at ``index``, in order."""
        return self._by_first_character.get(expr[index : index + 1], [])

    def at(self, expr: str, index: int) -> str | None:
        """The first form occurring in ``expr`` at ``index``."""
        return next((form for form in self.candidates(expr, index) if expr.startswith(form, index)), None)


_DIGITS_STAR_BRACKETS = frozenset("0123456789*()")
_DIGITS_BRACKETS_SPACE = frozenset("0123456789() ")


@cache
def _legacy_searches() -> dict[str, Search]:
    prefix_symbols = _Forms(prefix.symbol for prefix in SI_PREFIXES)
    unit_symbols = _Forms(unit.symbol for unit in ALL_UNITS)
    symbols = _Forms([*(prefix.symbol for prefix in SI_PREFIXES), *(unit.symbol for unit in ALL_UNITS)])
    long_forms = _Forms(
        [
            *(form for prefix in SI_PREFIXES for form in (prefix.name, *prefix.alternatives)),
            *(form for unit in ALL_UNITS for form in (unit.name, *unit.alternatives, *unit.plurals)),
        ]
    )

    def star_before_unit(expr: str, position: int) -> Span | None:
        # A "*" (not after another "*"), any spaces, a long form.
        for index in range(position, len(expr)):
            if expr[index] == "*" and (index == 0 or expr[index - 1] != "*"):
                after_spaces = len(expr) - len(expr[index + 1 :].lstrip(" "))
                if (form := long_forms.at(expr, after_spaces)) is not None:
                    return index, after_spaces + len(form)
        return None

    prefix_set = frozenset(form for prefix in SI_PREFIXES for form in (prefix.name, *prefix.alternatives))
    longest_prefix = max(map(len, prefix_set))

    def spaced_prefix(expr: str, position: int) -> Span | None:
        # A prefix, a space, a long form. Prefixes hold no spaces, so the first
        # space with a match has the leftmost one, and the longest prefix
        # ending at that space is the one a left-to-right search finds first.
        space = expr.find(" ", position)
        while space != -1:
            if (form := long_forms.at(expr, space + 1)) is not None:
                for index in range(max(position, space - longest_prefix), space):
                    if expr[index:space] in prefix_set:
                        return index, space + 1 + len(form)
            space = expr.find(" ", space + 1)
        return None

    def glued_symbol(expr: str, position: int) -> Span | None:
        # A digit, "*" or bracket, then a prefix or unit symbol.
        for index in range(position, len(expr)):
            if expr[index] in _DIGITS_STAR_BRACKETS and (symbol := symbols.at(expr, index + 1)) is not None:
                return index, index + 1 + len(symbol)
        return None

    def prefix_symbol_followed_by(mark: str) -> Search:
        # A digit, "*", bracket or space, a prefix symbol, then ``mark``.
        def search(expr: str, position: int) -> Span | None:
            for index in range(position, len(expr)):
                if expr[index] in _DIGITS_STAR_BRACKETS or expr[index] == " ":
                    for symbol in prefix_symbols.candidates(expr, index + 1):
                        after = index + 1 + len(symbol)
                        if expr.startswith(symbol, index + 1) and expr.startswith(mark, after):
                            return index, after + len(mark)
            return None

        return search

    def star_before_symbol(expr: str, position: int) -> Span | None:
        # A digit, bracket or space, "* ", then a unit symbol.
        for index in range(position, len(expr)):
            if (
                expr[index] in _DIGITS_BRACKETS_SPACE
                and expr.startswith("* ", index + 1)
                and (symbol := unit_symbols.at(expr, index + 3)) is not None
            ):
                return index, index + 3 + len(symbol)
        return None

    return {
        "star_before_unit": star_before_unit,
        "spaced_prefix": spaced_prefix,
        "glued_symbol": glued_symbol,
        "spaced_prefix_symbol": prefix_symbol_followed_by(" "),
        "starred_prefix_symbol": prefix_symbol_followed_by("* "),
        "star_before_symbol": star_before_symbol,
    }


def preprocess_legacy(expr: str) -> str:
    """The rewrites of the old ``legacy`` strictness, applied in order."""
    searches = _legacy_searches()

    # "newton*metre" -> "newton metre": "*UNIT" (but not "**UNIT") becomes " UNIT", after the first character
    # Searched in expr[1:], where expr[0] can't count as a "*" before the "*", as before. The rewrite
    # turns "*" into " ", so a "*" before the spaces it extends may now match: resume there.
    search = searches["star_before_unit"]
    head, tail = expr[:1], expr[1:]
    position = 0
    while (span := search(tail, position)) is not None:
        start, end = span
        tail = tail[:start] + tail[start:end].replace("*", " ") + tail[end:]
        position = start
        while position > 0 and tail[position - 1] == " ":
            position -= 1
        if position > 0 and tail[position - 1] == "*":
            position -= 1
    expr = head + tail

    # "kilo metre" -> "kilometre"
    expr = _rewrite_all(
        searches["spaced_prefix"], expr, lambda s, m: s[: m[0]] + " " + "".join(s[m[0] : m[1]].split()) + s[m[1] :]
    )
    # "100Pa" -> "100 Pa": space before a prefix or unit symbol after a digit, '*' or bracket
    expr = _rewrite_all(searches["glued_symbol"], expr, lambda s, m: s[: m[0] + 1] + " " + s[m[0] + 1 :])
    # "100 m Pa" -> "100 mPa"
    expr = _rewrite_all(
        searches["spaced_prefix_symbol"], expr, lambda s, m: s[: m[0] + 1] + s[m[0] : m[1] - 1] + s[m[1] :]
    )
    # "100 m* Pa" -> "100 mPa"
    expr = _rewrite_all(
        searches["starred_prefix_symbol"], expr, lambda s, m: s[: m[0] + 1] + s[m[0] : m[1] - 2] + s[m[1] :]
    )
    # "100* Pa" -> "100 Pa"
    return _rewrite_all(
        searches["star_before_symbol"], expr, lambda s, m: s[: m[0]] + s[m[0] : m[1]].replace("*", " ") + s[m[1] :]
    )


def transform_prefixes_to_standard(expr: str) -> str:
    """Rewrite alternative prefix spellings (``deka``, ``μ``, ...) as standard names, and collapse spaces.

    Works whether the prefix is attached to the unit (``μs``) or spaced from
    it (``μ s``).
    """
    for prefix in SI_PREFIXES:
        for alternative in prefix.alternatives:
            expr = _replace_prefix(expr, alternative, prefix.name)
    # Runs of two or more whitespace characters as one space.
    return "".join(
        " " if is_space and len(run) > 1 else run
        for is_space, run in ((is_space, "".join(chars)) for is_space, chars in groupby(expr, key=str.isspace))
    ).strip()


def _replace_prefix(expr: str, alternative: str, name: str) -> str:
    """``alternative`` as ``name`` where it starts a word and is followed (after any whitespace) by a letter."""
    pieces = []
    done = 0
    index = expr.find(alternative)
    while index != -1:
        after = index + len(alternative)
        while after < len(expr) and expr[after].isspace():
            after += 1
        starts_word = index == 0 or not (expr[index - 1].isalnum() or expr[index - 1] == "_")
        if starts_word and after < len(expr) and (expr[after] in ascii_letters or expr[after] in "\u00b5\u03a9"):
            pieces += [expr[done:index], name]
            done = after
            index = expr.find(alternative, after)
        else:
            index = expr.find(alternative, index + 1)
    pieces.append(expr[done:])
    return "".join(pieces)
