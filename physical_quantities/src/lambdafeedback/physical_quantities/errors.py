"""Exceptions raised by the physical quantities package."""

from __future__ import annotations

from lambdafeedback.expression_parsing import ExpressionParsingError


class QuantityError(ValueError):
    """Base class for errors raised by the physical quantities package.

    ``expression`` is the text being read, when known, and ``name`` (e.g.
    ``"response"``) identifies which quantity it was.
    """

    def __init__(self, message: str, *, expression: str | None = None, name: str | None = None) -> None:
        super().__init__(message)
        self.expression = expression
        self.name = name


class QuantityParseError(QuantityError):
    """A response could not be read as a physical quantity."""


class DisallowedUnitError(QuantityParseError):
    """A response used a unit from a unit set the task doesn't allow (``10 litre`` with only ``SI``).

    ``unit`` is the unit's name and ``unit_sets`` names the sets that contain it.
    """

    def __init__(
        self,
        message: str,
        *,
        unit: str | None = None,
        unit_sets: tuple[str, ...] = (),
        expression: str | None = None,
        name: str | None = None,
    ) -> None:
        super().__init__(message, expression=expression, name=name)
        self.unit = unit
        self.unit_sets = unit_sets


class UnitConversionError(QuantityError):
    """A quantity's unit could not be converted to SI base units."""


class QuantityParamsError(QuantityError, ExpressionParsingError):
    """A :class:`~lambdafeedback.physical_quantities.QuantityParams` field is invalid; ``field`` is its name.

    Also an ``ExpressionParsingError``, like the errors for the inherited
    :class:`~lambdafeedback.expression_parsing.ExpressionParams` fields.
    """

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"Invalid parameter {field!r}: {message}")
        self.field = field
        self.message = message

    def __reduce__(self) -> tuple[type[QuantityParamsError], tuple[str, str], dict[str, object]]:
        # The default would call cls(formatted_message), which doesn't match __init__.
        return type(self), (self.field, self.message), self.__dict__
