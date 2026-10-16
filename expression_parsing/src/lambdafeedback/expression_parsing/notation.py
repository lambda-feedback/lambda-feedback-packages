"""Notation in a response that is likely to be misread, such as ``^`` for a power under strict syntax.

Only the detection lives here: wording the warnings for a learner is up to
the caller, keyed by :class:`NotationWarning`.
"""

from __future__ import annotations

from enum import StrEnum


class NotationWarning(StrEnum):
    """A notation warning; the values are compareExpressions' feedback tags."""

    EXPONENT = "NOTATION_WARNING_EXPONENT"
    """``^`` under strict syntax, which doesn't read it as a power."""
    FACTORIAL = "NOTATION_WARNING_FACTORIAL"
    """``!`` under strict syntax, which doesn't read it as a factorial."""
    TRIPLE_FACTORIAL = "NOTATION_WARNING_TRIPLE_FACTORIAL"
    """``!!!``, which is never supported."""


def notation_warnings(response: str, strict_syntax: bool) -> list[NotationWarning]:
    """The notation warnings for ``response``, in the order of :class:`NotationWarning`.

    The checks look for the characters anywhere in ``response``, so under
    strict syntax ``!`` also warns for ``!=`` and ``!!!`` (which gets both
    factorial warnings).
    """
    warnings = []
    if strict_syntax and "^" in response:
        warnings.append(NotationWarning.EXPONENT)
    if strict_syntax and "!" in response:
        warnings.append(NotationWarning.FACTORIAL)
    if "!!!" in response:
        warnings.append(NotationWarning.TRIPLE_FACTORIAL)
    return warnings
