"""Regression tests for bugs carried over from the v0.1 extraction."""

import pytest
from sympy import Basic, simplify

from lambdafeedback.physical_quantities import (
    DisallowedUnitError,
    PhysicalQuantity,
    QuantityParams,
    QuantityParseError,
    RevertedUnit,
    build_quantity_parser,
    parse_quantity,
)
from lambdafeedback.physical_quantities._split import split_value_and_unit
from lambdafeedback.physical_quantities.quantity import _revert_value_text
from lambdafeedback.slr_parsing import GROUP_LABEL, ExprNode

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
        assert simplify(parse("60 angleminute").standard_values[0] - parse("1 degree").standard_values[0]) == 0


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

    @pytest.mark.parametrize("strictness", ["strict", "natural"])
    @pytest.mark.parametrize(
        "expr, unit",
        [
            ("2 Ω", "ohm"),
            ("2 𝛀", "ohm"),
            ("2 kΩ", "kiloohm"),
            ("2 MΩ", "megaohm"),
            ("2 mΩ", "milliohm"),
            ("2 O", "ohm"),
            ("2 kO", "kiloohm"),
            ("2 Ω m", "ohm metre"),
        ],
    )
    def test_ohm_symbols(self, expr, unit, strictness):
        # Only "O"/"kO" were recognised in strict mode, and only "kO" was a prefixed ohm in natural mode.
        assert parse_quantity(expr, QuantityParams(strictness=strictness)).unit.content_string() == unit

    @pytest.mark.parametrize("space", ["\xa0", " ", "\t", "\n", " "])
    def test_unicode_whitespace_separates_value_and_unit(self, space):
        # Only an ASCII space did: "2\xa0m" was the value "2\xa0m" with no unit.
        quantity = parse(f"2{space}m")
        assert (quantity.value.content_string(), quantity.unit.content_string()) == ("2", "metre")

    def test_zero_width_characters_are_ignored(self):
        assert parse("﻿2 m​").unit.content_string() == "metre"

    def test_long_run_of_letters_scans_quickly(self):
        # Natural mode tried every prefix of the rest of the word at each position:
        # cubic in its length, so 5000 letters took minutes.
        import time

        start = time.perf_counter()
        with pytest.raises(QuantityParseError):
            parse("x" * 5000 + " m")
        assert time.perf_counter() - start < 5

    @pytest.mark.parametrize("expr", ["2 " + "m*" * 2000 + "m", "2 " + " ".join(["m"] * 1500), "kg" * 3000])
    def test_deeply_nested_input_raises_quantity_parse_error(self, expr):
        # RecursionError escaped from the recursive steps.
        with pytest.raises(QuantityParseError, match="too long or too deeply nested"):
            parse(expr)

    def test_preview_without_calls_is_unchanged(self):
        assert parse("2 kg + 3").value_latex == r"2 \cdot g \cdot k + 3"

    def test_unit_between_value_parts_raises_instead_of_recursing_forever(self):
        # v0.1 rotated left and right alternately until RecursionError.
        with pytest.raises(QuantityParseError, match="Cannot separate the value from the unit"):
            parse("5 m/s x")

    @pytest.mark.parametrize(
        ("expr", "reverted"),
        [
            ("kg 2x", [("", "kg", " 2x")]),
            ("m 3y", [("", "m", " 3y")]),
            ("kg m 2x", [("kg", "kilogram metre", "m 2x"), ("", "kg", " m 2x"), ("kg ", "m", " 2x")]),
        ],
    )
    def test_strict_unit_before_juxtaposed_value_is_reverted_once(self, expr, reverted):
        # Splitting rotates the juxtaposition "2x" to the root; retagging it must strip the unit
        # from the "kg 2" it now holds, or that span is reported as a unit too ("kilogram 2").
        quantity = parse(expr, QuantityParams(strictness="strict"))
        assert quantity.value.content_string() == expr and quantity.unit is None
        assert quantity.reverted_units == tuple(RevertedUnit(*parts) for parts in reverted)


class TestReadingSteps:
    """The steps PhysicalQuantity.from_tree runs, each on a freshly parsed tree."""

    @staticmethod
    def tree(expr, params=NATURAL):
        parser = build_quantity_parser(params.unit_sets, params.strictness)
        return parser.parse(parser.scan(expr))[0], parser.tag_handler

    def test_split_raises_when_a_unit_is_between_value_parts(self):
        # The rotations change direction: there is no split.
        with pytest.raises(QuantityParseError, match="Cannot separate the value from the unit"):
            split_value_and_unit(*self.tree("5 m/s x"))

    def test_split_keeps_a_group_whole(self):
        root, value, unit = split_value_and_unit(*self.tree("(2 m)"))
        assert root.label == GROUP_LABEL and unit is root and value is None

    def test_split_returns_the_rotated_root(self):
        root, value, unit = split_value_and_unit(*self.tree("2 x m"))
        assert (value.content_string(), unit.content_string()) == ("2 x", "metre")
        assert root.children == [value, unit]

    def test_revert_value_text_reports_unit_like_parts(self):
        _, value, unit = split_value_and_unit(*self.tree("2 kg + 3"))
        assert unit is None
        # The first entry is the group enclosing the unit, with garbled text (a known issue, see the README).
        assert _revert_value_text(value) == (
            RevertedUnit(before="2", marked="2 kilogram", after="kg + 3"),
            RevertedUnit(before="2 ", marked="kg", after=" + 3"),
        )
        assert value.content_string() == "2 kg + 3"  # restored as typed

    def test_quantity_is_frozen(self):
        from dataclasses import FrozenInstanceError

        quantity = parse("5 km/h")
        with pytest.raises(FrozenInstanceError):
            quantity.value = None


class TestPickling:
    def test_params_error_round_trips(self):
        import pickle

        from lambdafeedback.physical_quantities import QuantityParamsError

        # The default reduce called QuantityParamsError(formatted_message), which needs two arguments.
        error = pickle.loads(pickle.dumps(QuantityParamsError("strictness", "bad")))
        assert (error.field, error.message, str(error)) == ("strictness", "bad", "Invalid parameter 'strictness': bad")

    def test_quantity_pickles_every_field_without_custom_state(self):
        import pickle
        from dataclasses import fields

        # The quantity no longer holds the parser (closures, which can't be pickled), so nothing is left out.
        assert "__getstate__" not in vars(PhysicalQuantity) and "__setstate__" not in vars(PhysicalQuantity)
        quantity = parse("5 km/h")
        copy = pickle.loads(pickle.dumps(quantity))

        def comparable(value):
            if isinstance(value, ExprNode):
                return value.content_string()
            if isinstance(value, tuple):
                return tuple(comparable(item) for item in value)
            if isinstance(value, Basic):
                # SymPy evaluates unevaluated expressions when unpickling (5*5/18 comes back as 25/18).
                return str(simplify(value))
            return value  # params, config, strings and RevertedUnits compare with ==

        for field in fields(PhysicalQuantity):
            assert comparable(getattr(copy, field.name)) == comparable(getattr(quantity, field.name)), field.name

    def test_parser_is_deprecated_and_still_the_cached_parser(self):
        from lambdafeedback.physical_quantities import build_quantity_parser

        quantity = parse("5 km/h")
        with pytest.deprecated_call(match="PhysicalQuantity.parser"):
            parser = quantity.parser
        assert parser is build_quantity_parser(quantity.params.unit_sets, quantity.params.strictness)

    def test_quantity_round_trips(self):
        import pickle

        quantity = parse("5 km/h")
        copy = pickle.loads(pickle.dumps(quantity))
        assert repr(copy) == repr(quantity)
        assert str(copy.base_dimension) == "length/time" and copy.unit_factor == quantity.unit_factor

    def test_quantity_deepcopy(self):
        import copy

        assert repr(copy.deepcopy(parse("5 km/h"))) == "PhysicalQuantity(value='5', unit='kilometre/hour')"

    def test_legacy_params_round_trip_without_warning_again(self):
        import pickle
        import warnings

        with pytest.deprecated_call():
            params = QuantityParams(legacy_preprocessing=True)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert pickle.loads(pickle.dumps(params)) == params


class TestHugeNumbers:
    @pytest.mark.parametrize("expr", ["1e999999 m", "2e-999999 kg", "1." + "1" * 100000 + " s"])
    def test_raise_quickly(self, expr):
        # The value's preview parses without rationalising, and Float('1e999999') took minutes.
        import time

        start = time.perf_counter()
        with pytest.raises(QuantityParseError):
            parse(expr)
        assert time.perf_counter() - start < 5


class TestInputLimits:
    def test_input_at_the_cap_is_read(self):
        from lambdafeedback.physical_quantities import MAX_INPUT_LENGTH

        expr = "2 m".ljust(MAX_INPUT_LENGTH)
        assert parse(expr).unit.content_string() == "metre"

    def test_input_over_the_cap_raises(self):
        from lambdafeedback.physical_quantities import MAX_INPUT_LENGTH

        with pytest.raises(QuantityParseError, match="too long"):
            parse("2 m".ljust(MAX_INPUT_LENGTH + 1))

    def test_preprocessing_passes_over_long_input_through(self):
        import time

        from lambdafeedback.physical_quantities import MAX_INPUT_LENGTH, preprocess_quantity

        expr = "5 μ s " * (MAX_INPUT_LENGTH // 6 + 1)
        start = time.perf_counter()
        assert preprocess_quantity(expr, NATURAL, name="response") == expr
        assert time.perf_counter() - start < 1

    def test_legacy_rewrites_skip_long_input(self):
        # "μ " * n needs about n²/2 rewrites (each moves a space one step left): cubic time.
        import time
        import warnings

        from lambdafeedback.physical_quantities import MAX_LEGACY_LENGTH, preprocess_quantity

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            legacy = QuantityParams(legacy_preprocessing=True)
        start = time.perf_counter()
        assert preprocess_quantity("μ " * (MAX_LEGACY_LENGTH // 2 + 1), legacy, name="response").startswith("μ μ")
        assert preprocess_quantity("100Pa", legacy, name="response") == "100 Pa"  # short input is still rewritten
        assert time.perf_counter() - start < 1

    def test_long_unit_chain_in_value_is_fast(self):
        # Each unit-tagged node's marked text walked its whole subtree: quadratic.
        import time

        start = time.perf_counter()
        with pytest.raises(QuantityParseError):
            parse("x m " * 2400)
        assert time.perf_counter() - start < 5


class TestUnitExponents:
    @pytest.mark.parametrize("expr", ["2 m^-1", "2 m^(-2)", "2 m^0.5", "2 m^(3/2)", "2 m^100", "2 km^2"])
    def test_ordinary_exponents(self, expr):
        assert parse(expr).unit is not None

    @pytest.mark.parametrize("expr", ["km^Pa^km", "2 km^Pa", "km^Pa"])
    def test_unit_as_exponent_raises(self, expr):
        # km^Pa^km hung: converting it evaluated 1000^(1000^1000).
        with pytest.raises(QuantityParseError, match="exponent must be a number"):
            parse(expr)

    @pytest.mark.parametrize("expr", ["2 km^101", "2 km^1000", "2 km^99999999", "2 m^99999999"])
    def test_huge_exponent_raises(self, expr):
        # 2 km^99999999 hung computing the factor 1000^99999999; 2 km^1000 failed with a digit-limit error.
        import time

        start = time.perf_counter()
        with pytest.raises(QuantityParseError, match="too large"):
            parse(expr)
        assert time.perf_counter() - start < 2


class TestUnitsOutsideTheUnitSets:
    """With only SI, 10 litre was the value 10*E*i*l*r*t: no unit, and e read as Euler's number."""

    SI_ONLY = QuantityParams(unit_sets=frozenset({"SI"}))

    @pytest.mark.parametrize(
        ("expr", "unit", "unit_sets"),
        [
            ("10 litre", "litre", ("common",)),
            ("2 litres", "litre", ("common",)),
            ("10 millilitre", "litre", ("common",)),
            ("3 feet", "foot", ("imperial",)),
            ("10 hour", "hour", ("common",)),
            ("5 °", "degree", ("common",)),
            ("2 m/hour", "hour", ("common",)),
        ],
    )
    @pytest.mark.parametrize("strictness", ["natural", "strict"])
    def test_spelled_out_unit_raises(self, expr, unit, unit_sets, strictness):
        params = self.SI_ONLY.replace(strictness=strictness)
        with pytest.raises(DisallowedUnitError) as caught:
            parse(expr, params)
        assert (caught.value.unit, caught.value.unit_sets) == (unit, unit_sets)
        assert caught.value.expression == expr
        assert isinstance(caught.value, QuantityParseError)

    @pytest.mark.parametrize("expr", ["5 h", "2 L", "2 a m", "2 x_bar m", "sin(x) m"])
    def test_symbols_and_other_words_are_still_values(self, expr):
        # A letter such as h or L is more likely a variable than an hour or a litre.
        parse(expr, self.SI_ONLY)

    def test_latex_command_is_not_a_word(self):
        params = self.SI_ONLY.replace(is_latex=True)
        with pytest.raises(DisallowedUnitError):
            parse(r"2~\text{litre}", params)
        assert parse(r"\frac{1}{2}~\mathrm{m}", params).unit is not None

    def test_selected_sets_are_allowed(self):
        assert parse("10 litre").unit.content_string() == "litre"

    def test_error_pickles(self):
        import pickle

        with pytest.raises(DisallowedUnitError) as caught:
            parse("10 litre", self.SI_ONLY)
        copy = pickle.loads(pickle.dumps(caught.value))
        assert (copy.unit, copy.unit_sets, copy.expression, str(copy)) == (
            "litre",
            ("common",),
            "10 litre",
            str(caught.value),
        )
