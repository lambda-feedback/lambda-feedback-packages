"""Tests for the typed API introduced in 0.2.0: parameters, configuration, conventions, LaTeX."""

import pytest
from sympy import E, I, Symbol

from lambdafeedback.expression_parsing import (
    ExpressionParams,
    ExpressionParsingError,
    InvalidParameterError,
    LatexParseError,
    NotationWarning,
    SymbolAssumptionError,
    SymbolSpec,
    SympyParsingConfig,
    UnknownConventionError,
    apply_convention,
    convention_parser,
    is_complex_number_on_cartesian_form,
    is_complex_number_on_exponential_form,
    is_number,
    notation_warnings,
    parse_expression,
    parse_expressions,
    parse_latex,
    parse_symbol_assumptions,
    sanitise_latex,
)


class TestExpressionParams:
    def test_defaults_match_the_evaluation_function_defaults(self):
        params = ExpressionParams()
        assert (params.complex_numbers, params.convention, params.elementary_functions, params.strict_syntax) == (
            False,
            "equal_precedence",
            False,
            False,
        )
        assert params.rationalise is True

    def test_from_dict_maps_json_names_and_ignores_unrelated_keys(self):
        params = ExpressionParams.from_dict(
            {"complexNumbers": True, "specialFunctions": True, "strict_syntax": True, "atol": 0.1, "criteria": "x"}
        )
        assert (params.complex_numbers, params.special_functions, params.strict_syntax) == (True, True, True)

    def test_symbols_are_normalised_once(self):
        params = ExpressionParams.from_dict(
            {
                "symbols": {
                    "x": {"latex": "x", "aliases": [" xx ", "", "  "]},
                    " ": {"latex": "blank", "aliases": ["b"]},
                    "lambda": {"latex": r"\Lambda", "aliases": ["lam"]},
                }
            }
        )
        assert params.symbols == {
            "x": SymbolSpec("x", ("xx",)),
            "lamda": SymbolSpec(r"\Lambda", ("lam", "lambda")),
        }

    def test_lamda_always_exists(self):
        assert ExpressionParams().symbols == {"lamda": SymbolSpec(r"\lambda", ("lambda",))}

    def test_normalisation_is_idempotent(self):
        params = ExpressionParams.from_dict({"symbols": {"lambda": {"latex": "L", "aliases": ["lam"]}}})
        assert params.replace(simplify=True).symbols == params.symbols

    def test_legacy_input_symbols(self):
        params = ExpressionParams.from_dict({"input_symbols": [["x", ["xx", " "]], [" ", ["y"]], []]})
        assert params.input_symbols == (("x", ("xx",)),)

    def test_symbol_assumptions_string_is_parsed(self):
        params = ExpressionParams.from_dict({"symbol_assumptions": "('a','positive') ('f','function')"})
        assert params.symbol_assumptions == (("a", "positive"), ("f", "function"))

    @pytest.mark.parametrize("text", ["('a')", "('a', 'b', 'c')", "(1, 2)", "('a', 'positive'"])
    def test_malformed_symbol_assumptions(self, text):
        with pytest.raises(SymbolAssumptionError) as info:
            parse_symbol_assumptions(text)
        assert info.value.text is not None

    def test_unknown_convention(self):
        with pytest.raises(UnknownConventionError, match="Unknown convention") as info:
            ExpressionParams(convention="sideways")
        assert info.value.convention == "sideways"
        assert isinstance(info.value, ExpressionParsingError)

    def test_params_are_immutable(self):
        with pytest.raises(AttributeError):
            ExpressionParams().strict_syntax = True
        with pytest.raises(TypeError):
            ExpressionParams().symbols["x"] = SymbolSpec("x")  # type: ignore[index]

    @pytest.mark.parametrize(
        ("params", "name"),
        [
            ({"complexNumbers": "false"}, "complex_numbers"),
            ({"strict_syntax": 1}, "strict_syntax"),
            ({"reserved_keywords": "abc"}, "reserved_keywords"),
            ({"unsplittable_symbols": [1]}, "unsplittable_symbols"),
            ({"symbols": {"x": {"aliases": "xy"}}}, "symbols"),
            ({"symbols": {"x": {"latex": 1}}}, "symbols"),
            ({"symbols": ["x"]}, "symbols"),
            ({"input_symbols": [["x", "xy"]]}, "input_symbols"),
            ({"plus_minus": 1}, "plus_minus"),
        ],
    )
    def test_parameter_types_are_checked(self, params, name):
        with pytest.raises(InvalidParameterError) as info:
            ExpressionParams.from_dict(params)
        assert info.value.name == name
        assert isinstance(info.value, ExpressionParsingError)


class TestSympyParsingConfig:
    def test_multi_character_symbols_and_reserved_keywords_are_unsplittable(self):
        params = ExpressionParams.from_dict({"symbols": {"bc": {"latex": "b_c"}}, "reserved_keywords": ["resp"]})
        config = SympyParsingConfig.from_params(params, unsplittable_symbols=["metre"])
        assert config.unsplittable_symbols == ("metre", "resp", "bc", "lamda")
        assert str(parse_expression("a/bc", config)) == "a/bc"

    def test_special_names_are_plain_symbols_unless_enabled(self):
        plain = SympyParsingConfig.from_params(ExpressionParams())
        enabled = SympyParsingConfig.from_params(ExpressionParams(complex_numbers=True, elementary_functions=True))
        assert plain.symbol_dict["I"] == Symbol("I") and enabled.symbol_dict["I"] == I
        assert plain.symbol_dict["E"] == Symbol("E") and enabled.symbol_dict["E"] == E

    def test_replace_gives_a_new_config(self):
        config = SympyParsingConfig.from_params(ExpressionParams())
        assert config.replace(strict_syntax=True).params.strict_syntax is True
        assert config.params.strict_syntax is False

    def test_replace_changes_own_fields_and_params_together(self):
        config = SympyParsingConfig.from_params(ExpressionParams())
        changed = config.replace(simplify=False, extra_unsplittable_symbols=("ab",))
        assert changed.params.simplify is False
        assert changed.extra_unsplittable_symbols == ("ab",)
        assert "ab" in changed.unsplittable_symbols and changed.symbol_dict["ab"] == Symbol("ab")
        assert config.extra_unsplittable_symbols == ()

    def test_plus_minus_parses_to_both_expressions_in_order(self):
        config = SympyParsingConfig.from_params(ExpressionParams())
        x = Symbol("x")
        # Parsed unevaluated (x - 1 stays x - 1*1), so compare evaluated forms.
        assert [e.doit() for e in parse_expressions("x plus_minus 1", config)] == [x + 1, x - 1]

    def test_parse_expression_rejects_several_expressions(self):
        config = SympyParsingConfig.from_params(ExpressionParams())
        with pytest.raises(ExpressionParsingError, match="stands for 2 expressions"):
            parse_expression("{x, y}", config)
        assert parse_expression("{x, x}", config) == Symbol("x")  # the same expression twice is one


class TestConventions:
    def test_parser_is_built_once_per_convention(self):
        assert convention_parser("equal_precedence") is convention_parser("equal_precedence")
        assert convention_parser("equal_precedence") is not convention_parser("implicit_higher_precedence")

    @pytest.mark.parametrize(
        ("convention", "expected"),
        [("equal_precedence", "a/bc"), ("implicit_higher_precedence", "a/(bc)"), (None, "a/bc")],
    )
    def test_apply_convention(self, convention, expected):
        assert apply_convention("a/bc", convention) == expected


class TestLatex:
    def test_parse_latex_maps_task_symbols(self):
        symbols = {"x_1": SymbolSpec("x_{1}")}
        assert parse_latex(r"x_{1}^2", symbols) == "x_1**2"

    def test_parse_latex_plus_minus(self):
        assert parse_latex(r"1 \pm x", {}) == "{1 - x, x + 1}"

    def test_unparseable_symbol_latex(self):
        with pytest.raises(LatexParseError, match="symbol") as info:
            parse_latex("x", {"x": SymbolSpec(r"\frac{")})
        assert info.value.symbol == r"\frac{"

    def test_sanitise_latex_unwraps_text(self):
        assert sanitise_latex(r"3 \mathrm{kg}~\text{m}") == "3kg m"


def test_number_forms():
    assert is_number("3.5")
    assert is_complex_number_on_cartesian_form("1+2*I")
    assert is_complex_number_on_exponential_form("2*exp(3*I)")
    assert not is_number("x")


class TestNotationWarnings:
    @pytest.mark.parametrize(
        "response, strict, expected",
        [
            ("x**2", True, []),
            ("x^2", True, [NotationWarning.EXPONENT]),
            ("x^2", False, []),
            ("n!", True, [NotationWarning.FACTORIAL]),
            ("n!", False, []),
            ("x != y", True, [NotationWarning.FACTORIAL]),
            ("n!!!", False, [NotationWarning.TRIPLE_FACTORIAL]),
            ("n!!!", True, [NotationWarning.FACTORIAL, NotationWarning.TRIPLE_FACTORIAL]),
            ("x^n!", True, [NotationWarning.EXPONENT, NotationWarning.FACTORIAL]),
        ],
    )
    def test_warnings(self, response, strict, expected):
        assert notation_warnings(response, strict) == expected

    def test_values_are_the_compare_expressions_tags(self):
        assert [str(warning) for warning in NotationWarning] == [
            "NOTATION_WARNING_EXPONENT",
            "NOTATION_WARNING_FACTORIAL",
            "NOTATION_WARNING_TRIPLE_FACTORIAL",
        ]
