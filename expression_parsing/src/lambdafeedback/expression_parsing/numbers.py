"""Recognising how numbers are written: plain numbers, complex forms, number patterns."""

from __future__ import annotations

import re
from collections.abc import Callable

DEFAULT_SIGNIFICANT_FIGURES = 2

NONNEGATIVE_NUMBER_REGEX = r"((0|[1-9]\d*)?(\.\d+)?(?<=\d)(e-?(0|[1-9]\d*))?)"
"""A non-negative decimal, optionally with an ``e`` exponent."""

NUMBER_REGEX = r"(-?(0|[1-9]\d*)?(\.\d+)?(?<=\d)( *(e|E|\*10\^|\*10\*\*)-?(0|[1-9]\d*))?)"
"""A decimal, optionally with an exponent written ``e``, ``E``, ``*10^`` or ``*10**``."""


def is_number(string: str) -> bool:
    match = re.fullmatch(NUMBER_REGEX, string)
    return match is not None and len(match.group(0)) > 0


def is_complex_number_on_cartesian_form(string: str) -> bool:
    """``a+b*I`` (either part may be missing)."""
    string = "".join(string.split())
    return re.fullmatch(NUMBER_REGEX + r"?\+?" + NUMBER_REGEX + r"?\*?I?", string) is not None


def is_complex_number_on_exponential_form(string: str) -> bool:
    """``a*E^(b*I)``, ``a*E**(b*I)`` or ``a*exp(b*I)``."""
    string = "".join(string.split())
    return re.fullmatch(NUMBER_REGEX + r"?\*?(E\^|E\*\*|exp)\(?" + NUMBER_REGEX + r"*\*?I\)?", string) is not None


def escape_regex_reserved_characters(string: str) -> str:
    """Backslash-escape regex metacharacters.

    Unlike ``re.escape`` this leaves spaces alone:
    :func:`generate_arbitrary_number_pattern_matcher` strips whitespace from
    the escaped text afterwards, and an escaped space would leave a stray
    backslash behind.
    """
    string = string.replace("\\", "\\\\")
    for char in "+*?^$.[]{}()|/":
        string = string.replace(char, "\\" + char)
    return string


def generate_arbitrary_number_pattern_matcher(string: str) -> Callable[[str], bool]:
    """A matcher accepting strings written like ``string`` with any numbers in place of its numbers.

    E.g. the pattern ``"2x+3"`` matches ``"10x+0.5"`` but not ``"x+3"``.
    Whitespace is ignored.
    """
    non_numbers = []
    number_pattern = "(\\(" + NUMBER_REGEX + "\\))"
    full_pattern = "(" + number_pattern + "|" + NONNEGATIVE_NUMBER_REGEX + ")"
    number = re.search(number_pattern, string)
    nonneg_number = re.search(NONNEGATIVE_NUMBER_REGEX, string)
    offset = 0
    while number is not None or nonneg_number is not None:
        start_number = number.span()[0] if number is not None else len(string)
        start_nonneg_number = nonneg_number.span()[0] if nonneg_number is not None else len(string)
        match = number if start_number < start_nonneg_number else nonneg_number
        assert match is not None
        start, end = (position + offset for position in match.span())
        non_number = escape_regex_reserved_characters(string[offset:start])
        if non_number:
            non_number = "(" + non_number + ")"
        non_numbers.append("".join(non_number.split()))
        offset = end
        number = re.search(number_pattern, string[offset:])
        nonneg_number = re.search(NONNEGATIVE_NUMBER_REGEX, string[offset:])
    tail = escape_regex_reserved_characters(string[offset:])
    if tail:
        tail = "(" + tail + ")"
    non_numbers.append("".join(tail.split()))
    pattern = full_pattern.join(non_numbers)

    def matcher(comp_string: str) -> bool:
        return re.fullmatch(pattern, "".join(comp_string.split())) is not None

    return matcher


def compute_relative_tolerance_from_significant_decimals(string: str) -> float:
    """``5 * 10**-n`` for a number written with ``n`` significant figures (at least 2); 0 for non-numbers."""
    string = string.strip()
    if re.fullmatch(NUMBER_REGEX, string) is None:
        return 0
    # The mantissa ends where the exponent starts: "e", "E", "*10^" or "*10**".
    mantissa = re.split(r" *[eE*]", string, maxsplit=1)[0]
    significant_characters = mantissa.replace(".", "").lstrip("-0")
    return float(5 * 10 ** (-max(len(significant_characters), DEFAULT_SIGNIFICANT_FIGURES)))
