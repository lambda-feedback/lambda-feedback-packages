"""Recognising how numbers are written: plain numbers, complex forms, number patterns.

A number is a decimal (``12``, ``0.5``, ``.5``; no leading zeros), optionally
signed and with an exponent written ``e``, ``E``, ``*10^`` or ``*10**``
(``-1.5e3``, ``2 *10^3``). The scanners below are greedy and never backtrack:
each optional piece of a number starts with a different character, so a
shorter reading never lets more of the text match.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

DEFAULT_SIGNIFICANT_FIGURES = 2

_EXPONENT_MARKS = ("e", "E", "*10^", "*10**")
# Sets, not strings: "" is in every string, and slicing past the end gives "".
_DIGITS = frozenset("0123456789")
_NONZERO_DIGITS = _DIGITS - {"0"}


def _digits_end(string: str, index: int) -> int:
    """Where the run of digits at ``index`` ends."""
    while index < len(string) and string[index].isdecimal():
        index += 1
    return index


def _integer_end(string: str, index: int) -> int:
    """Where the integer at ``index`` ends: ``0``, or digits not starting with ``0`` (``index`` if none)."""
    if string.startswith("0", index):
        return index + 1
    if string[index : index + 1] in _NONZERO_DIGITS:
        return _digits_end(string, index + 1)
    return index


def _starts_fraction(string: str, index: int) -> bool:
    return string.startswith(".", index) and string[index + 1 : index + 2].isdecimal()


def _mantissa_end(string: str, index: int) -> int | None:
    """Where the unsigned decimal at ``index`` (``12``, ``0.5``, ``.5``) ends, if there is one."""
    end = _integer_end(string, index)
    if end == index and not _starts_fraction(string, index):
        return None
    return _digits_end(string, end + 1) if _starts_fraction(string, end) else end


def _number_end(string: str, index: int, *, nonnegative: bool = False) -> int | None:
    """Where the number at ``index`` ends, if there is one.

    ``nonnegative`` numbers have no sign and only an ``e`` exponent, with no spaces before it.
    """
    start = index + 1 if not nonnegative and string.startswith("-", index) else index
    end = _mantissa_end(string, start)
    if end is None:
        return None
    marks = ("e",) if nonnegative else _EXPONENT_MARKS
    mark_start = end if nonnegative else len(string) - len(string[end:].lstrip(" "))
    mark = next((mark for mark in marks if string.startswith(mark, mark_start)), None)
    if mark is not None:
        exponent_start = mark_start + len(mark)
        if string.startswith("-", exponent_start):
            exponent_start += 1
        exponent_end = _integer_end(string, exponent_start)
        if exponent_end > exponent_start:
            end = exponent_end
    return end


def plain_number_end(string: str, index: int = 0, *, signed: bool = False) -> int | None:
    """Where a plainly written number at ``index`` ends (``12``, ``0.5``, ``.5``, ``2e-3``), if there is one.

    Plainly written: only an ``e`` exponent, with no spaces before it, and a
    leading ``-`` only if ``signed``. See :func:`is_number` for the full forms.
    """
    start = index + 1 if signed and string.startswith("-", index) else index
    return _number_end(string, start, nonnegative=True)


def _after_number(string: str, index: int, *, nonnegative: bool = False) -> int:
    """Past the number at ``index``, or ``index`` if there is none."""
    end = _number_end(string, index, nonnegative=nonnegative)
    return index if end is None else end


def _after(string: str, index: int, *texts: str) -> int:
    """Past the first of ``texts`` at ``index``, or ``index`` if none is there."""
    found = next((text for text in texts if string.startswith(text, index)), "")
    return index + len(found)


def is_number(string: str) -> bool:
    """True if ``string`` is exactly one number (e.g. ``-1.5e3``, ``2*10^3``)."""
    return _number_end(string, 0) == len(string)


def is_complex_number_on_cartesian_form(string: str) -> bool:
    """``a+b*I`` (either part may be missing, but not both)."""
    string = "".join(string.split())
    if string in ("", "+"):
        return False
    index = _after_number(string, 0)
    index = _after(string, index, "+")
    index = _after_number(string, index)
    index = _after(string, index, "*")
    return _after(string, index, "I") == len(string)


def is_complex_number_on_exponential_form(string: str) -> bool:
    """``a*E^(b*I)``, ``a*E**(b*I)`` or ``a*exp(b*I)``."""
    string = "".join(string.split())
    index = _after_number(string, 0)
    index = _after(string, index, "*")
    after_base = _after(string, index, "E^", "E**", "exp")
    if after_base == index:
        return False
    index = _after(string, after_base, "(")
    index = _after_number(string, index)
    index = _after(string, index, "*")
    if not string.startswith("I", index):
        return False
    return _after(string, index + 1, ")") == len(string)


def _bracketed_number_end(string: str, index: int) -> int | None:
    """Past ``(number)`` at ``index``, if it is there."""
    if not string.startswith("(", index):
        return None
    end = _number_end(string, index + 1)
    return end + 1 if end is not None and string.startswith(")", end) else None


def _next_number(string: str, offset: int) -> tuple[int, int] | None:
    """The first number in ``string`` at or after ``offset``: a non-negative number, or a bracketed one before it."""
    nonnegative_start = next(
        (index for index in range(offset, len(string)) if string[index] in _DIGITS or _starts_fraction(string, index)),
        None,
    )
    limit = len(string) if nonnegative_start is None else nonnegative_start
    bracket = string.find("(", offset, limit)
    while bracket != -1:
        if (end := _bracketed_number_end(string, bracket)) is not None:
            return bracket, end
        bracket = string.find("(", bracket + 1, limit)
    if nonnegative_start is None:
        return None
    # A digit (or "." and a digit) always starts a number, so this is never the fallback.
    end = _after_number(string, nonnegative_start, nonnegative=True)
    return nonnegative_start, end


def generate_arbitrary_number_pattern_matcher(string: str) -> Callable[[str], bool]:
    """A matcher accepting strings written like ``string`` with any numbers in place of its numbers.

    E.g. the pattern ``"2x+3"`` matches ``"10x+0.5"`` but not ``"x+3"``.
    Whitespace is ignored. In place of a number, the matcher accepts a
    bracketed number (``(-2)``) or else a non-negative one.
    """
    texts = []
    offset = 0
    while (number := _next_number(string, offset)) is not None:
        texts.append("".join(string[offset : number[0]].split()))
        offset = number[1]
    texts.append("".join(string[offset:].split()))

    def matcher(comp_string: str) -> bool:
        comp_string = "".join(comp_string.split())
        index = 0
        for position, text in enumerate(texts):
            if position > 0:
                end = _bracketed_number_end(comp_string, index) or _number_end(comp_string, index, nonnegative=True)
                if end is None:
                    return False
                index = end
            if not comp_string.startswith(text, index):
                return False
            index += len(text)
        return index == len(comp_string)

    return matcher


@dataclass(frozen=True)
class WrittenNumber:
    """A number as written, digit for digit: what its precision is depends on how it was written.

    ``92`` and ``92.00`` are the same value written to 2 and 4 significant
    figures; ``540`` has 2 and ``540.`` (with a point) 3.
    """

    integer: str
    """The digits before the point (may be empty, as in ``.5``)."""
    fraction: str
    """The digits after the point (may be empty)."""
    has_point: bool
    exponent: int = 0

    @property
    def significant_figures(self) -> int:
        """Leading zeros don't count; trailing zeros count only after a written point. Zero has 1."""
        digits = (self.integer + self.fraction).lstrip("0")
        if not digits:
            return 1
        if not self.has_point:
            digits = digits.rstrip("0")
        return len(digits) or 1

    @property
    def decimal_places(self) -> int:
        """The digits after the point, less the exponent: ``5.02e4`` has 0, ``5e-3`` has 3."""
        return max(len(self.fraction) - self.exponent, 0)


def read_written_number(string: str) -> WrittenNumber | None:
    """``string`` as a :class:`WrittenNumber`, if it is exactly one decimal number; ``None`` otherwise.

    More lenient than :func:`is_number`, since a learner's precision is read
    from what they wrote: a ``+`` sign, leading zeros and a trailing point
    (``540.``) are allowed. The exponent is written as in :func:`is_number`
    (``e``, ``E``, ``*10^`` or ``*10**``), with an optional sign.
    """
    string = string.strip()
    index = 1 if string[:1] in ("+", "-") else 0
    integer_end = _digits_end(string, index)
    has_point = string.startswith(".", integer_end)
    fraction_end = _digits_end(string, integer_end + 1) if has_point else integer_end
    integer, fraction = string[index:integer_end], string[integer_end + 1 : fraction_end]
    if not integer and not fraction:
        return None
    exponent = 0
    if fraction_end < len(string):
        mark = next((mark for mark in _EXPONENT_MARKS if string.startswith(mark, fraction_end)), None)
        if mark is None:
            return None
        exponent_text = string[fraction_end + len(mark) :]
        digits = exponent_text[1:] if exponent_text[:1] in ("+", "-") else exponent_text
        if not digits or _digits_end(digits, 0) != len(digits):
            return None
        exponent = int(exponent_text)
    return WrittenNumber(integer, fraction, has_point, exponent)


def round_to_significant_figures(value: float, figures: int) -> float:
    """``value`` rounded to ``figures`` significant figures (``3.14159`` to 3 is ``3.14``)."""
    return float(f"{value:.{figures}g}")


def round_to_decimal_places(value: float, places: int) -> str:
    """``value`` rounded to ``places`` decimal places, as a string to keep trailing zeros (``0`` to 2 is ``0.00``)."""
    return f"{value:.{places}f}"


def compute_relative_tolerance_from_significant_decimals(string: str) -> float:
    """``5 * 10**-n`` for a number written with ``n`` significant figures (at least 2); 0 for non-numbers."""
    string = string.strip()
    if not is_number(string):
        return 0.0
    start = 1 if string.startswith("-") else 0
    mantissa = string[start : _mantissa_end(string, start)]
    significant_characters = mantissa.replace(".", "").lstrip("0")
    return float(5 * 10 ** (-max(len(significant_characters), DEFAULT_SIGNIFICANT_FIGURES)))
