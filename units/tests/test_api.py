"""Tests for the typed units API introduced in 0.2.0."""

import pytest
from sympy import Rational, simplify

import lambdafeedback.units
from lambdafeedback.expression_parsing import ExpressionParsingError
from lambdafeedback.units import (
    ALL_UNITS,
    CONVERSION_TO_BASE_SI,
    SI_BASE_UNITS,
    SI_PREFIXES,
    UNIT_SETS,
    QuantityError,
    QuantityParams,
    QuantityParamsError,
    QuantityParseError,
    QuantityTag,
    RevertedUnit,
    build_quantity_parser,
    parse_quantity,
    preprocess_quantity,
    units_in,
)


def test_version():
    assert isinstance(lambdafeedback.units.__version__, str)


class TestQuantityParams:
    def test_defaults(self):
        params = QuantityParams()
        assert (params.strictness, params.legacy_preprocessing, params.unit_sets) == (
            "natural",
            False,
            frozenset({"SI", "common", "imperial"}),
        )

    def test_from_dict_maps_legacy_and_units_string(self):
        with pytest.deprecated_call():
            params = QuantityParams.from_dict(
                {"strictness": "legacy", "units_string": "SI imperial", "complexNumbers": True}
            )
        assert params.strictness == "natural" and params.legacy_preprocessing is True
        assert params.unit_sets == {"SI", "imperial"}
        assert params.complex_numbers is True

    def test_it_is_expression_params(self):
        from lambdafeedback.expression_parsing import ExpressionParams

        assert isinstance(QuantityParams(), ExpressionParams)
        assert isinstance(QuantityParams().replace(simplify=True), QuantityParams)

    def test_unknown_strictness(self):
        with pytest.raises(ExpressionParsingError, match="strictness") as info:
            QuantityParams(strictness="lenient")
        assert isinstance(info.value, QuantityParamsError) and info.value.field == "strictness"

    @pytest.mark.parametrize("unit_sets", [{"si"}, {"SI", "metric"}, "SI"])
    def test_unknown_unit_sets(self, unit_sets):
        with pytest.raises(QuantityParamsError, match="unit_sets"):
            QuantityParams(unit_sets=unit_sets)

    def test_unit_sets_accepts_any_set(self):
        assert QuantityParams(unit_sets={"SI"}).unit_sets == frozenset({"SI"})
        assert QuantityParams(unit_sets=frozenset()).unit_sets == frozenset()

    @pytest.mark.parametrize(
        "units_string, expected",
        [
            ("SI common imperial", {"SI", "common", "imperial"}),
            ("SI, imperial", {"SI", "imperial"}),
            (" common ", {"common"}),
            ("", set()),
        ],
    )
    def test_from_dict_units_string(self, units_string, expected):
        assert QuantityParams.from_dict({"units_string": units_string}).unit_sets == expected

    @pytest.mark.parametrize("units_string", ["SIcommon", "SI metric", ["SI"]])
    def test_from_dict_rejects_unknown_units_string(self, units_string):
        with pytest.raises(QuantityParamsError):
            QuantityParams.from_dict({"units_string": units_string})


class TestData:
    def test_named_fields(self):
        metre = next(unit for unit in SI_BASE_UNITS if unit.name == "metre")
        assert (metre.symbol, metre.dimension, metre.alternatives, metre.plurals) == (
            "m",
            "length",
            ("meter",),
            ("metres", "meters"),
        )
        kilo = next(prefix for prefix in SI_PREFIXES if prefix.name == "kilo")
        assert (kilo.symbol, kilo.factor) == ("k", "(10**3)")

    def test_units_in_deduplicates_in_table_order(self):
        units = units_in(frozenset({"SI", "common"}))
        assert len(units) == len(set(units))
        assert units[: len(SI_BASE_UNITS)] == SI_BASE_UNITS
        assert set(units_in(frozenset({"imperial"}))) == set(UNIT_SETS["imperial"])

    def test_conversion_to_base_si(self):
        assert CONVERSION_TO_BASE_SI["metre"] == "metre"
        assert CONVERSION_TO_BASE_SI["kilometre"] == "((10**3)*metre)"
        assert CONVERSION_TO_BASE_SI["newton"] == "(metre*kilogram*second**(-2))"
        assert "kilokilometre" not in CONVERSION_TO_BASE_SI

    def test_public_tables_are_read_only(self):
        with pytest.raises(TypeError):
            UNIT_SETS["mine"] = ()  # type: ignore[index]
        with pytest.raises(TypeError):
            CONVERSION_TO_BASE_SI["metre"] = "2*metre"  # type: ignore[index]

    def test_unit_names_are_unique(self):
        names = [unit.name for unit in ALL_UNITS]
        assert len(names) == len(set(names))

    @pytest.mark.parametrize("unit", ALL_UNITS, ids=lambda unit: unit.name)
    def test_every_unit_converts_to_si_base_units(self, unit):
        quantity = parse_quantity(f"1 {unit.name}", QuantityParams())
        assert quantity.unit is not None
        base_names = {base.name for base in SI_BASE_UNITS}
        assert {str(symbol) for symbol in quantity.expanded_unit.free_symbols} <= base_names


def _si_value(text):
    return parse_quantity(text, QuantityParams()).standard_value


class TestConversions:
    @pytest.mark.parametrize(
        "left, right",
        [
            ("60 angleminute", "1 degree"),
            ("60 anglesecond", "1 angleminute"),
            ("180 degree", "pi radian"),
            ("1 radian", "1"),
            ("1 h", "60 min"),
            ("1 day", "24 hour"),
            ("1 L", "1 dm^3"),
            ("1 km", "1000 m"),
            ("1 N", "1 kg m/s^2"),
            ("1 J", "1 N m"),
            ("1 W", "1 J/s"),
            ("1 Pa", "1 N/m^2"),
            ("1 C", "1 A s"),
            ("1 V", "1 W/A"),
            ("1 bar", "100000 Pa"),
            ("1 ft", "12 in"),
            ("1 yd", "3 ft"),
            ("1 mi", "1760 yd"),
            ("1 gal", "8 pt"),
            ("1 lb", "16 oz"),
            ("1 st", "14 lb"),
            ("1 roentgen", "0.000258 C/kg"),
        ],
    )
    def test_equal_quantities(self, left, right):
        assert simplify(_si_value(left) - _si_value(right)) == 0


class TestErrors:
    @pytest.mark.parametrize("text", ["", "   ", "(", "2 m)", "2 ((m", "10 kg *", "2 m/s/", "5 m/s x"])
    def test_unreadable_input_raises_quantity_parse_error(self, text):
        with pytest.raises(QuantityParseError) as info:
            parse_quantity(text, QuantityParams(), name="answer")
        assert (info.value.expression, info.value.name) == (text, "answer")

    def test_parser_errors_are_chained(self):
        from lambdafeedback.slr_parsing import SLRError

        with pytest.raises(QuantityParseError) as info:
            parse_quantity("2 m)", QuantityParams())
        assert isinstance(info.value.__cause__, SLRError)

    @pytest.mark.parametrize("text", ["2 x;y", "2 x="])
    def test_unparseable_value_raises_quantity_parse_error(self, text):
        with pytest.raises(QuantityParseError) as info:
            parse_quantity(text, QuantityParams())
        assert isinstance(info.value.__cause__, ExpressionParsingError)


class TestParser:
    def test_parsers_are_cached_per_unit_sets_and_strictness(self):
        sets = frozenset({"SI"})
        assert build_quantity_parser(sets, "strict") is build_quantity_parser(sets, "strict")
        assert build_quantity_parser(sets, "strict") is not build_quantity_parser(sets, "natural")

    def test_tags(self):
        quantity = parse_quantity("9.81 m/s^2", QuantityParams())
        assert QuantityTag.NUMBER in quantity.value.tags
        assert quantity.unit.tags == {QuantityTag.UNIT}


class TestPhysicalQuantity:
    def test_value_unit_and_si_forms(self):
        quantity = parse_quantity("5 km/h", QuantityParams())
        assert (quantity.value.content_string(), quantity.unit.content_string()) == ("5", "kilometre/hour")
        # The dimension keeps the unit's conversion factor (symbols are declared positive).
        assert str(quantity.dimension.simplify()) == "5*length/(18*time)"
        assert quantity.unit_factor == Rational(5, 18)
        assert str(quantity.standard_unit) == "metre/second"
        assert quantity.latex == r"5~\frac{\mathrm{kilometre}}{\mathrm{hour}}"

    def test_unit_only_and_value_only(self):
        assert parse_quantity("kg", QuantityParams()).value is None
        assert parse_quantity("2x", QuantityParams()).unit is None

    def test_reverted_unit_messages(self):
        quantity = parse_quantity("2 kg + 3", QuantityParams())
        assert all(isinstance(reverted, RevertedUnit) for reverted in quantity.reverted_units)
        # Known quirk (as in v0.1): the enclosing group is reported too, with garbled positions.
        assert quantity.reverted_units[-1] == RevertedUnit(before="2 ", marked="kg", after=" + 3")

    def test_strict_mode_rejects_natural_spellings(self):
        assert parse_quantity("2 metres", QuantityParams(strictness="strict")).unit is None
        assert parse_quantity("2 metres", QuantityParams(strictness="natural")).unit.content_string() == "metre"

    def test_repr(self):
        assert repr(parse_quantity("5 km/h", QuantityParams())) == "PhysicalQuantity(value='5', unit='kilometre/hour')"
        assert repr(parse_quantity("kg", QuantityParams())) == "PhysicalQuantity(value=None, unit='kilogram')"

    def test_parse_errors_are_quantity_errors(self):
        with pytest.raises(QuantityParseError) as info:
            parse_quantity("10 kg *", QuantityParams())
        assert isinstance(info.value, QuantityError) and isinstance(info.value, ValueError)


class TestPreprocessing:
    def test_same_shape_as_expression_preprocessing(self):
        assert preprocess_quantity("response", "5 μ s", QuantityParams()) == "5 micros"

    def test_legacy(self):
        with pytest.deprecated_call():
            legacy_params = QuantityParams(legacy_preprocessing=True)
        assert preprocess_quantity("response", "100Pa", legacy_params) == "100 Pa"
        assert preprocess_quantity("response", "newton*metre", legacy_params) == "newton metre"
