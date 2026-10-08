"""Regression tests for bugs carried over from the v0.1 extraction."""

import re
import subprocess
import sys
import warnings

import pytest
from sympy import Abs, Function, Integral, Symbol, sqrt

from lambdafeedback.expression_parsing import (
    AbsoluteValueNotationError,
    BracketNotationError,
    ExpressionParams,
    ExpressionParsingError,
    InvalidParameterError,
    LatexParseError,
    SymbolAssumptionError,
    SympyParsingConfig,
    compute_relative_tolerance_from_significant_decimals,
    convert_absolute_notation,
    create_expression_set,
    is_number,
    parse_expression,
    parse_latex,
    preprocess_expression,
    substitute_input_symbols,
    sympy_to_latex,
)


def parsing_params(**overrides):
    return SympyParsingConfig.from_params(ExpressionParams.from_dict(overrides))


class TestOnlyMathematicsIsEvaluated:
    """parse_expr evals its input; it used to see Python's builtins (open, __import__, ...)."""

    @pytest.mark.parametrize("strict_syntax", [False, True])
    @pytest.mark.parametrize("convention", [None, "equal_precedence"])
    @pytest.mark.parametrize(
        "response",
        [
            "__import__('sys').modules.__setitem__('pwned_by_response', 1)",
            "sin(\"__import__('sys').modules.__setitem__('pwned_by_response', 1)\")",
            "Number(\"__import__('sys').modules.__setitem__('pwned_by_response', 1)\")",
            "S('x')",
            "open('/dev/null')",
            "x.func",
            "().__class__.__bases__",
        ],
    )
    def test_code_is_rejected(self, response, convention, strict_syntax):
        config = parsing_params(convention=convention, strict_syntax=strict_syntax)
        with pytest.raises(ExpressionParsingError):
            parse_expression(response, config)
        assert "pwned_by_response" not in sys.modules

    def test_non_mathematical_sympy_names_are_plain_symbols(self):
        config = parsing_params(strict_syntax=True, convention=None)
        assert parse_expression("plot(x)", config) == Function("plot")(Symbol("x"))

    def test_mathematical_names_still_resolve(self):
        config = parsing_params(elementary_functions=True)
        x, y = Symbol("x"), Symbol("y")
        assert parse_expression("sqrt(x)+abs(y)", config) == sqrt(x) + Abs(y)
        assert parse_expression("Integral(x, x)", config) == Integral(x, x)
        assert parse_expression("2x3", config).equals(6 * x)  # split_symbols emits Number('3')

    def test_symbol_aliases_are_not_executed(self):
        symbols = ExpressionParams.from_dict(
            {
                "symbols": {
                    "x": {"latex": "x", "aliases": ["__import__('sys').modules.__setitem__('pwned_by_alias', 1)"]}
                }
            }
        ).symbols
        parse_latex("x", symbols)
        assert "pwned_by_alias" not in sys.modules


class TestParseExpressionErrors:
    @pytest.mark.parametrize("response", ["", "x**", "(x", "x)("])
    def test_invalid_input_raises_expression_parsing_error(self, response):
        with pytest.raises(ExpressionParsingError) as info:
            parse_expression(response, parsing_params())
        assert info.value.expression is not None


class TestSymbolAssumptions:
    def test_assumption_tuples_are_not_executed(self):
        injected = "(__import__('sys').modules.__setitem__('pwned_by_assumptions', 1), 'positive')"
        with pytest.raises(ValueError):
            parsing_params(symbol_assumptions=injected)
        assert "pwned_by_assumptions" not in sys.modules

    def test_assumption_names_must_be_identifiers(self):
        with pytest.raises(SymbolAssumptionError, match="positive=True") as info:
            parsing_params(symbol_assumptions="('x', 'positive=True')")
        assert (info.value.symbol, info.value.assumption) == ("x", "positive=True")

    def test_valid_assumptions_still_apply(self):
        params = parsing_params(symbol_assumptions="('a','positive') ('f','function') ('c','constant')")
        assert params.symbol_dict["a"].is_positive
        assert params.symbol_dict["f"](1).func.__name__ == "f"
        assert "c" in params.constants


class TestParsing:
    def test_capital_e_after_implicit_multiplication(self):
        # Fixed in slr_parsing (the convention parser scanned "E" as a grammar symbol).
        assert str(parse_expression("2E", parsing_params())) == "2*E"
        assert str(parse_expression("xE", parsing_params())) == "E*x"

    def test_chained_equalities_are_rejected(self):
        with pytest.raises(ValueError, match="="):
            parse_expression("a=b=c", parsing_params())

    def test_arithmetic_on_sets_is_rejected_in_strict_syntax(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            with pytest.raises(ValueError, match="set"):
                parse_expression("{x+1}*{x-1}", parsing_params(strict_syntax=True))

    def test_parsing_params_default_missing_keys(self):
        assert SympyParsingConfig.from_params(ExpressionParams.from_dict({})).complex_numbers is False

    def test_lone_plus_minus(self):
        assert sorted(create_expression_set("plus_minus", ExpressionParams())) == ["", "-"]


class TestInputSymbols:
    def test_user_defined_lambda_survives_repeated_substitution(self):
        params = ExpressionParams.from_dict({"symbols": {"lambda": {"latex": r"\Lambda_0", "aliases": ["lam"]}}})
        assert substitute_input_symbols(["lam"], params) == ["lamda"]
        assert substitute_input_symbols(["lam"], params) == ["lamda"]

    def test_empty_aliases_do_not_remove_real_ones(self):
        params = ExpressionParams.from_dict({"symbols": {"x": {"latex": "x", "aliases": ["", "", "xx"]}}})
        assert substitute_input_symbols(["xx"], params) == ["x"]

    def test_aliases_are_stripped(self):
        params = ExpressionParams.from_dict({"symbols": {"x": {"latex": "x", "aliases": [" xx "]}}})
        assert substitute_input_symbols(["xx"], params) == ["x"]


class TestNoSideEffects:
    def test_sympy_to_latex_does_not_mutate_settings(self):
        settings = {"mul_symbol": r" \cdot "}
        sympy_to_latex(parse_expression("2x", parsing_params()), {}, settings=settings)
        assert settings == {"mul_symbol": r" \cdot "}

    def test_parse_latex_reports_errors_cleanly(self, capsys):
        parse_latex("x", ExpressionParams.from_dict({"symbols": {"x": {"latex": "x", "aliases": ["1+"]}}}).symbols)
        assert capsys.readouterr().out == ""
        with pytest.raises(ValueError) as info:
            parse_latex(r"\frac{x", {})
        assert len(info.value.args) == 1


class TestSanitiseLatex:
    def test_unclosed_wrapper_raises_instead_of_hanging(self):
        # Run in a subprocess: the v0.1 code loops forever on this input.
        script = (
            "from lambdafeedback.expression_parsing import LatexParseError, sanitise_latex\n"
            "try:\n"
            "    sanitise_latex(r'3 \\mathrm{kg')\n"
            "except LatexParseError as e:\n"
            "    print('raised:', e, e.wrapper, e.response)\n"
        )
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=30)
        assert result.stdout.startswith(r"raised: Unclosed \mathrm{")
        assert result.stdout.strip().endswith(r"\mathrm 3\mathrm{kg")


class TestLatexEquations:
    def test_equation_parses_to_eq_on_any_latex2sympy_build(self):
        # PyPI's latex2sympy2 reads "x = 2" as an assignment (returning 2); the
        # lambda-feedback fork compareExpressions uses returns Eq(x, 2).
        assert parse_latex("x = 2", {}) == "Eq(x, 2)"
        assert parse_latex(r"\frac{x}{2} = y + 1", {}) == "Eq(x/2, y + 1)"

    def test_more_than_one_equals_sign_is_rejected(self):
        with pytest.raises(LatexParseError, match="=") as info:
            parse_latex("x = y = 2", {})
        assert info.value.expression == "x = y = 2"


class TestPublicReleaseReview:
    """Bugs found reviewing the package for its public release."""

    def test_multiple_answers_split_at_top_level_commas_only(self):
        assert create_expression_set("{f(x,y), 2}", ExpressionParams()) == ["f(x,y)", "2"]

    def test_times_ten_to_the_power_is_a_number(self):
        assert is_number("2*10^3")

    @pytest.mark.parametrize("number", ["1.5e3", "1.5E3", "1.5*10^3", "1.5*10**3", "1.5 e3"])
    def test_relative_tolerance_counts_mantissa_digits_only(self, number):
        assert compute_relative_tolerance_from_significant_decimals(number) == pytest.approx(0.05)

    def test_bracket_error_reports_what_was_written(self):
        with pytest.raises(BracketNotationError, match=re.escape("'[x+y)'")) as info:
            preprocess_expression("response", "[x+y)", ExpressionParams())
        assert (info.value.original, info.value.expression) == ("[x+y)", "(x+y)")

    @pytest.mark.parametrize("expr", ["x|", "|x|+|"])
    def test_unpaired_pipe_is_reported(self, expr):
        with pytest.raises(AbsoluteValueNotationError):
            convert_absolute_notation(expr, "response")

    @pytest.mark.parametrize("response", [r"1\pm\sqrt{2}", r"1 \pm \sqrt{2}", r"1\pm{\sqrt{2}}"])
    def test_latex_plus_minus_without_a_space(self, response):
        assert parse_latex(response, {}) == "{1 + sqrt(2), 1 - sqrt(2)}"

    def test_latex_plus_minus_does_not_rewrite_the_latex(self):
        # The ± expansion used to run symbol substitution over the LaTeX, so \lambda became \lamda.
        both = sorted([parse_latex(r"1 + \lambda", {}), parse_latex(r"1 - \lambda", {})])
        assert parse_latex(r"1 \pm \lambda", {}) == "{" + ", ".join(both) + "}"


class TestPythonKeywords:
    """Python keywords can't be names in SymPy's eval; they used to fail or be mangled."""

    @pytest.mark.parametrize(
        ("response", "expected"),
        [("in", "i*n"), ("2*is + 1", "2*i*s + 1"), ("x if", "f*i*x"), ("as", "a*s"), ("True", "T*e*r*u")],
    )
    def test_keywords_are_read_like_other_words(self, response, expected):
        assert str(parse_expression(response, parsing_params())) == expected

    def test_keywords_are_single_symbols_with_strict_syntax(self):
        assert parse_expression("2*in", parsing_params(strict_syntax=True)) == 2 * Symbol("in")

    def test_as_inside_a_name_is_not_split_with_strict_syntax(self):
        # The old 'as' -> 'a*s' rule was a substring replacement: 'phase' became 'pha*se'.
        assert parse_expression("phase", parsing_params(strict_syntax=True, convention=None)) == Symbol("phase")

    @pytest.mark.parametrize("code", ["in", "as", "del", "lambda_1"])
    def test_keyword_like_symbol_codes_keep_their_symbol(self, code):
        params = ExpressionParams.from_dict(
            {"symbols": {code: {"latex": "Q", "aliases": ["q"]}}, "symbol_assumptions": f"('{code}', 'positive')"}
        )
        parsed = parse_expression(
            preprocess_expression("response", "2q", params), SympyParsingConfig.from_params(params)
        )
        assert sympy_to_latex(parsed, params.symbols) == "2 Q"
        assert all(symbol.is_positive for symbol in parsed.free_symbols)

    def test_lambda_and_lamda_cannot_both_be_defined(self):
        with pytest.raises(InvalidParameterError, match="lamda"):
            ExpressionParams.from_dict({"symbols": {"lambda": {"latex": "A"}, "lamda": {"latex": "B"}}})

    def test_symbols_with_assumptions_keep_their_latex(self):
        params = ExpressionParams.from_dict(
            {"symbols": {"vx": {"latex": "v_x"}}, "symbol_assumptions": "('vx', 'positive')"}
        )
        parsed = parse_expression("2*vx", SympyParsingConfig.from_params(params))
        assert sympy_to_latex(parsed, params.symbols) == "2 v_x"


class TestFunctionNames:
    """Short function names matched inside ordinary words; unapplied functions gave unhelpful errors."""

    @pytest.mark.parametrize("word", ["area", "time", "rest", "interval", "pressure", "free", "design"])
    def test_short_function_names_inside_words_are_letters(self, word):
        parsed = parse_expression(
            preprocess_expression("response", word, ExpressionParams(elementary_functions=True)),
            parsing_params(elementary_functions=True),
        )
        assert not parsed.atoms(Function)
        assert {str(symbol) for symbol in parsed.free_symbols} <= set(word) | {"E"}

    @pytest.mark.parametrize(
        ("response", "expected"),
        [
            ("re(z)+im(z)", "re(z) + im(z)"),
            ("xmax(a, b)", "x*Max(a, b)"),
            ("sec^2(x)", "sec(x)**2"),
            ("max (a, b)", "Max(a, b)"),
        ],
    )
    def test_short_function_names_still_apply(self, response, expected):
        params = ExpressionParams(elementary_functions=True)
        assert (
            str(
                parse_expression(
                    preprocess_expression("response", response, params), parsing_params(elementary_functions=True)
                )
            )
            == expected
        )

    def test_short_function_name_as_a_task_symbol(self):
        params = ExpressionParams.from_dict({"symbols": {"max": {"latex": "M"}}})
        assert parse_expression(
            preprocess_expression("response", "2max", params), SympyParsingConfig.from_params(params)
        ) == 2 * Symbol("max")

    @pytest.mark.parametrize(
        ("response", "function"), [("sin", "sin"), ("sin x", "sin"), ("2sqrtx", "sqrt"), ("abs", "Abs")]
    )
    def test_function_without_brackets_says_so(self, response, function):
        params = ExpressionParams(elementary_functions=True)
        with pytest.raises(ExpressionParsingError, match=re.escape(f"{function} is a function")):
            parse_expression(
                preprocess_expression("response", response, params), parsing_params(elementary_functions=True)
            )

    def test_declared_function_without_brackets_says_so(self):
        with pytest.raises(ExpressionParsingError, match="f is a function"):
            parse_expression("f x", parsing_params(symbol_assumptions="('f', 'function')"))

    @pytest.mark.parametrize("response", ["int(x, x)", "xmax(a, b)"])
    def test_unrecognised_function_arguments_are_not_called_a_set(self, response):
        # Without elementary_functions these multiply by the tuple (a, b); the message used to blame a set.
        with pytest.raises(ExpressionParsingError, match="bracketed list") as info:
            parse_expression(response, parsing_params())
        assert "set" not in str(info.value)
