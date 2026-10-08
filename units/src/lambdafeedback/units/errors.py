"""Exceptions raised by the units package."""

from __future__ import annotations

from lambdafeedback.expression_parsing import ExpressionParsingError


class QuantityError(ValueError):
    """Base class for errors raised by the units package.

    ``expression`` is the text being read, when known, and ``name`` (e.g.
    ``"response"``) identifies which quantity it was.
    """

    def __init__(self, message: str, *, expression: str | None = None, name: str | None = None) -> None:
        super().__init__(message)
        self.expression = expression
        self.name = name


class QuantityParseError(QuantityError):
    """A response could not be read as a physical quantity."""


class UnitConversionError(QuantityError):
    """A quantity's unit could not be converted to SI base units."""


class QuantityParamsError(QuantityError, ExpressionParsingError):
    """A :class:`~lambdafeedback.units.QuantityParams` field is invalid; ``field`` is its name.

    Also an ``ExpressionParsingError``, like the errors for the inherited
    :class:`~lambdafeedback.expression_parsing.ExpressionParams` fields.
    """

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"Invalid parameter {field!r}: {message}")
        self.field = field
