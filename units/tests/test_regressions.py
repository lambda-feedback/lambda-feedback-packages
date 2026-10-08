"""Regression tests for bugs carried over from the v0.1 extraction."""

import pytest
from sympy import simplify

from lambdafeedback.units import QuantityParams, QuantityParseError, parse_quantity

NATURAL = QuantityParams(strictness="natural")


def parse(expr, params=NATURAL):
    return parse_quantity(expr, params)


class TestUnitData:
    @pytest.mark.parametrize("plural", ["litres", "liters"])
    def test_litre_plurals(self, plural):
        quantity = parse(f"2 {plural}")
        assert quantity.unit.content_string() == "litre"

    def test_nautical_mile_plural(self):
        # Was "2 nautical_mile second": only the misspelt "nauticalmiles" was a plural.
        assert parse("2 nautical_miles").unit.content_string() == "nautical_mile"

    def test_roentgen_is_charge_per_mass(self):
        # Was kelvin per kilogram.
        assert str(parse("1 roentgen").standard_unit) == "ampere*second/gram"

    def test_angle_units_share_one_base(self):
        # Degrees and radians were in turns but arcminutes in radians, so 60' != 1°.
        assert parse("1 radian").unit_factor == 1
        assert simplify(parse("60 angleminute").standard_value - parse("1 degree").standard_value) == 0


class TestParsing:
    @pytest.mark.parametrize("expr", ["(2 m) s", "(2 m) (s)", "(x m) s"])
    def test_grouped_quantity_followed_by_a_unit(self, expr):
        # Groups are atomic: as for "(2 m)" alone, the whole input is the unit.
        quantity = parse(expr)
        assert quantity.value is None
        assert quantity.unit.content_string() == quantity.ast_root.content_string()

    def test_unit_between_value_parts_raises_instead_of_recursing_forever(self):
        # v0.1 rotated left and right alternately until RecursionError.
        with pytest.raises(QuantityParseError, match="Cannot separate the value from the unit"):
            parse("5 m/s x")
