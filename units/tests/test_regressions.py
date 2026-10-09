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

    @pytest.mark.parametrize("elementary_functions", [False, True])
    @pytest.mark.parametrize(
        "expr, latex",
        [
            ("sin(2)", r"\sin{\left(2 \right)}"),
            ("2 sin(x)", r"2 \cdot \sin{\left(x \right)}"),
            ("sin(-10.5*4)", r"\sin{\left(\left(-10.5\right) \cdot 4 \right)}"),
        ],
    )
    def test_value_preview_keeps_function_calls(self, expr, latex, elementary_functions):
        # The preview reserved the unit symbols "s" and "in", showing sin(2) as s·in·2
        # while the value itself was parsed (and graded) as sin(2).
        params = QuantityParams(elementary_functions=elementary_functions)
        assert parse_quantity(expr, params).value_latex == latex

    @pytest.mark.parametrize("strictness", ["strict", "natural"])
    @pytest.mark.parametrize("expr", ["2 m 3 s", "1 hour 30 minutes", "3 m 2", "m 2"])
    def test_number_inside_unit_raises(self, expr, strictness):
        # "2 m 3 s" was unit "metre 3 second", dimension length*3*time.
        with pytest.raises(QuantityParseError, match="Cannot separate the value from the unit"):
            parse_quantity(expr, QuantityParams(strictness=strictness))

    @pytest.mark.parametrize(
        "expr, unit",
        [
            ("2 1/s", "1/second"),
            ("2 m^2 s", "metre^2 second"),
            ("2 m^(1/2)", "metre^(1/2)"),
            ("2 m s^-2", "metre second^-2"),
            ("1/s", "1/second"),
        ],
    )
    def test_numbers_allowed_in_units(self, expr, unit):
        assert parse(expr).unit.content_string() == unit

    @pytest.mark.parametrize("expr", ["2 °C", "20deg C", "5 degrees F", "3 ℃", "3 ℉"])
    def test_celsius_and_fahrenheit_raise(self, expr):
        # "2 °C" was read as 2 degree·coulomb.
        with pytest.raises(QuantityParseError, match="Celsius or Fahrenheit"):
            parse(expr)

    @pytest.mark.parametrize("expr", ["2 °", "10 deg", "10 degrees"])
    def test_plain_degrees_still_parse(self, expr):
        assert parse(expr).unit.content_string() == "degree"

    @pytest.mark.parametrize("sign", ["·", "⋅", "×"])
    def test_product_signs(self, sign):
        quantity = parse(f"2{sign}10^3 kg{sign}m")
        assert (quantity.value.content_string(), quantity.unit.content_string()) == ("2*10^3", "kilogram*metre")

    @pytest.mark.parametrize(
        "expr, value, unit",
        [
            ("2~m", "2", "metre"),
            (r"2~\mathrm{m}", "2", "metre"),
            (r"2\,\mathrm{m}", "2", "metre"),
            (r"\sqrt{2}~\text{m}", r"\sqrt{2}", "metre"),
            (r"9.81~\mathrm{m}/\mathrm{s}^2", "9.81", "metre/second^2"),
            (r"\frac{1}{2}~\mathrm{kg}", r"\frac{1}{2}", "kilogram"),
        ],
    )
    def test_latex_spacing_and_upright_units(self, expr, value, unit):
        # MathLive's "2~\mathrm{m}" raised; "2~m" was read as the value 2*m with no unit.
        quantity = parse_quantity(expr, QuantityParams(is_latex=True))
        assert (quantity.value.content_string(), quantity.unit.content_string()) == (value, unit)

    def test_preview_without_calls_is_unchanged(self):
        assert parse("2 kg + 3").value_latex == r"2 \cdot g \cdot k + 3"

    def test_unit_between_value_parts_raises_instead_of_recursing_forever(self):
        # v0.1 rotated left and right alternately until RecursionError.
        with pytest.raises(QuantityParseError, match="Cannot separate the value from the unit"):
            parse("5 m/s x")
