"""Regression tests for bugs carried over from the v0.1 extraction."""

import math
import re
import subprocess
import sys
import warnings

import pytest
from sympy import Abs, Eq, Function, Integral, Symbol, sqrt

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
    def test_equation_parses_on_any_latex2sympy_build(self):
        # PyPI's latex2sympy2 reads "x = 2" as an assignment (returning 2).
        assert parse_latex("x = 2", {}) == "x = 2"
        assert parse_latex(r"\frac{x}{2} = y + 1", {}) == "x/2 = y + 1"

    @pytest.mark.parametrize("elementary_functions", [False, True])
    def test_equation_round_trips_through_parse_expression(self, elementary_functions):
        # "Eq(x, 2)" didn't: with elementary_functions the E of Eq is Euler's number.
        params = ExpressionParams(elementary_functions=elementary_functions)
        text = parse_latex(r"y = 2x + 1", params.symbols)
        parsed = parse_expression(
            preprocess_expression("response", text, params), SympyParsingConfig.from_params(params)
        )
        assert str(parsed) == "Eq(y, 2*x + 1)"

    def test_simplify_keeps_an_equation(self):
        # Simplifying the Eq as a whole turned "x = x" into "True".
        assert parse_latex("x = x", {}, simplify=True) == "x = x"

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


class TestEquations:
    def test_sides_are_left_unevaluated_like_a_whole_expression(self):
        x = Symbol("x")
        assert str(parse_expression("x+x=2", parsing_params())) == "Eq(x + x, 2)"
        assert parse_expression("x+x=2", parsing_params(simplify=True)) == Eq(2 * x, 2, evaluate=False)

    def test_huge_powers_in_an_equation_are_not_evaluated(self):
        # Evaluating the sides used to compute 9**(9**9), which never finished.
        assert str(parse_expression("9**9**9=x", parsing_params())) == "Eq(9**(9**9), x)"


@pytest.mark.parametrize("expression", ["a/", ")("])
def test_apply_convention_raises_expression_parsing_error(expression):
    from lambdafeedback.expression_parsing import apply_convention

    with pytest.raises(ExpressionParsingError):
        apply_convention(expression, "equal_precedence")


class TestNumberForms:
    def test_exponential_form_check_is_not_exponential_time(self):
        # The number regex could match the empty string, and the check repeated it: 26 digits took >10 s.
        from lambdafeedback.expression_parsing import is_complex_number_on_exponential_form

        assert not is_complex_number_on_exponential_form("2*exp(" + "1" * 5000 + "x")

    @pytest.mark.parametrize("string", ["", " ", "+"])
    def test_nothing_is_not_a_cartesian_complex_number(self, string):
        from lambdafeedback.expression_parsing import is_complex_number_on_cartesian_form

        assert not is_complex_number_on_cartesian_form(string)

    @pytest.mark.parametrize("string", ["1+2*I", "-1.5+2I", "3", "I", "2*I", "1e3+2*10^3*I"])
    def test_cartesian_forms_still_match(self, string):
        from lambdafeedback.expression_parsing import is_complex_number_on_cartesian_form

        assert is_complex_number_on_cartesian_form(string)

    def test_pattern_matcher_is_not_polynomial_time(self):
        # Numbers separated only by spaces became adjacent slots that re-split long digit runs.
        from lambdafeedback.expression_parsing import generate_arbitrary_number_pattern_matcher

        assert not generate_arbitrary_number_pattern_matcher("1 2 3")("1" * 1000 + "x")


@pytest.mark.parametrize(("response", "character"), [("√x", "√"), ("½", "½"), ("2∠x", "∠")])
def test_unreadable_characters_are_reported_as_unrecognised(response, character):
    # They used to fail as "A string or other literal is not allowed", which the learner didn't write.
    with pytest.raises(ExpressionParsingError, match=re.escape(f"Unrecognised character {character!r}")):
        parse_expression(response, parsing_params())


@pytest.mark.parametrize(
    ("unicode", "ascii"),
    [
        ("x − 1", "x - 1"),
        ("x – 1", "x - 1"),
        ("2×3", "2*3"),
        ("6÷2", "6/2"),
        ("2·x", "2*x"),
        ("2x² + 3x − 1", "2x**2 + 3x - 1"),
        ("x⁻¹", "x**(-1)"),
        ("x^²", "x**2"),
        ("(x+1)³", "(x+1)**3"),
        ("sin²(x)", "sin(x)**2"),
    ],
)
def test_unicode_operators_parse_like_ascii(unicode, ascii):
    params = ExpressionParams(elementary_functions=True)
    config = SympyParsingConfig.from_params(params)
    parse = lambda text: parse_expression(preprocess_expression("response", text, params), config)  # noqa: E731
    assert parse(unicode) == parse(ascii)


class TestLatexEulerLetter:
    """latex2sympy2 read E/e inconsistently, and the E/e workaround corrupted commands and leaked its placeholder."""

    @pytest.mark.parametrize(
        ("latex", "expected"),
        [
            ("2E", "2*E"),  # read as an empty exponent: 2
            (r"\epsilon E", "E*epsilon"),  # E dropped
            ("e_1 e_2", "e_1*e_2"),  # read as Euler's number: E
            ("x_{E}", "x_E"),  # placeholder leaked: x_a
            (r"E_0 \times 2", "2*E_0"),  # \times corrupted to \timas: failed
            ("e^{x}", "e**x"),  # Euler's number is left to parse_expression's elementary_functions
        ],
    )
    def test_e_and_E_are_symbols(self, latex, expected):
        assert parse_latex(latex, {}) == expected

    @pytest.mark.parametrize("latex", ["2E5", "2e5", "1.5e-3", "1.5E-3"])
    def test_scientific_notation_is_a_number(self, latex):
        assert parse_latex(latex, {}) == str(
            parse_expression(latex.replace("e", "E").replace("E", "e"), parsing_params())
        )

    def test_task_symbols_with_e_in_their_latex(self):
        from lambdafeedback.expression_parsing import SymbolSpec

        assert parse_latex("E_{k} + 1", {"Ek": SymbolSpec("E_{k}")}) == "Ek + 1"


class TestPickling:
    """``symbols`` is a read-only mappingproxy, which pickle and deepcopy couldn't handle."""

    def params(self):
        return ExpressionParams(
            symbols={"x": {"latex": r"\chi", "aliases": ["X"]}},
            symbol_assumptions=(("f", "function"),),
            elementary_functions=True,
        )

    def test_params_round_trip(self):
        import pickle

        params = self.params()
        copy = pickle.loads(pickle.dumps(params))
        assert copy == params
        with pytest.raises(TypeError):
            copy.symbols["y"] = None  # still read-only

    def test_params_deepcopy(self):
        import copy

        params = self.params()
        assert copy.deepcopy(params) == params

    def test_config_round_trip_parses_the_same(self):
        import pickle

        config = SympyParsingConfig.from_params(self.params())
        expected = parse_expression("f(x) + sin(x)", config)  # also fills the cached substitution_params
        assert parse_expression("f(x) + sin(x)", pickle.loads(pickle.dumps(config))) == expected


class TestNumberSizeLimits:
    """Number literals SymPy can't handle in reasonable time are rejected before evaluation."""

    @pytest.mark.parametrize("rationalise", [True, False])
    @pytest.mark.parametrize(
        "expr, message",
        [
            ("1e999999", "exponent"),  # Float: minutes; Rational: an integer too long for str()
            ("1e-999999", "exponent"),
            ("2.5e1001 + x", "exponent"),
            ("a.5e5000", "exponent"),  # Python reads .5e5000 as a number after the name a
            ("1e999999j", "exponent"),
            ("1e" + "9" * 5000, "exponent"),
            ("1." + "1" * 100000, "digits"),  # Float of a 100000-digit mantissa: minutes
            ("1" * 5000, "digits"),  # over Python's 4300-digit limit: was "Invalid syntax"
            ("1" * 1200, "digits"),
        ],
    )
    def test_too_large(self, expr, message, rationalise):
        config = SympyParsingConfig.from_params(ExpressionParams(rationalise=rationalise))
        with pytest.raises(ExpressionParsingError, match=message):
            parse_expression(expr, config)

    @pytest.mark.parametrize("expr", ["1e1000", "1e-1000", "2.5E+1000", "6.022e23", "1" * 1000, "1_000_000", ".5e3"])
    def test_within_the_limits(self, expr):
        assert parse_expression(expr, parsing_params()) is not None

    def test_names_that_look_like_numbers_are_not_checked(self):
        config = SympyParsingConfig.from_params(ExpressionParams(symbols={"x2e9999": {"latex": "y"}}))
        assert str(parse_expression("x2e9999", config)) == "x2e9999"

    def test_powers_stay_unevaluated(self):
        # Only literals are limited; 10^999999 is a Pow, not a computed number.
        assert str(parse_expression("2*10^999999", parsing_params())) == "2*10**999999"


class TestSubstitutionScaling:
    def test_long_input_with_many_substitutions_is_fast(self):
        # Every substitution was tried at every position, and FunctionName copied the
        # rest of the input on each check: 100000 characters x 1000 names took over 10 s.
        import time

        from lambdafeedback.expression_parsing.substitution import FunctionName, substitute

        substitutions = [(f"name{k}", f"N{k}") for k in range(1000)] + [(FunctionName("sin"), "SIN")]
        text = "x" * 100000 + " sin(x) name7"
        start = time.perf_counter()
        result = substitute(text, substitutions)
        assert time.perf_counter() - start < 2
        assert result.endswith(" SIN(x) N7")

    def test_first_match_order_is_kept(self):
        from lambdafeedback.expression_parsing.substitution import substitute

        assert substitute("abc bc c", [("abc", "p"), ("bc", "q"), ("c", "r")]) == "p q r"
        assert substitute("abc", [("a", "1"), ("abc", "2")]) == "1bc"  # the listed order wins, not length
        assert substitute("sin(x) sinx", [(("sin", ["("]), "S")]) == "S(x) sinx"


class TestLatexBackend:
    """latex2sympy2 → latex2sympy2_extended: no module state, \\left/\\right, exact decimals, Greek gamma as symbols."""

    def test_a_differential_does_not_break_later_parses(self):
        # latex2sympy2 overwrote its module-level `var` on \mathrm{d}x; every later parse in the
        # process then failed. A subprocess, so no earlier test can have masked it.
        script = (
            "from lambdafeedback.expression_parsing import parse_latex\n"
            "parse_latex(r'\\int x \\mathrm{d}x', {})\n"
            "print(parse_latex('2x', {}), parse_latex(r'\\hat{x} + 1', {}))\n"
        )
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=60)
        assert result.stdout.split()[0] == "2*x", result.stderr

    @pytest.mark.parametrize(
        ("latex", "expected"),
        [
            (r"\tan\left(\frac{\pi}{4}\right)", "tan(pi/4)"),
            (r"\left|x-1\right|", "Abs(x - 1)"),
            ("9.81", "981/100"),  # not the Float 9.81000000000000
            ("1.5e-3", "3/2000"),
            (r"\gamma", "gamma"),  # not EulerGamma
            (r"\gamma_1 + \Gamma", "Gamma + gamma_1"),  # \gamma_1 failed to parse
            (r"\mathrm{kg}", "kg"),  # was "\mathrm{kg}", which parse_expression can't read
            (r"2\frac{1}{2}", "5/2"),  # a mixed number (was 2*1/2)
        ],
    )
    def test_latex_forms(self, latex, expected):
        assert parse_latex(latex, {}) == expected

    @pytest.mark.parametrize("latex", ["2)", r"\pi\right)", "y}"])
    def test_malformed_latex_is_rejected(self, latex):
        # latex2sympy2 silently dropped everything after the error (2) gave 2).
        with pytest.raises(LatexParseError):
            parse_latex(latex, {})

    def test_comma_list_is_several_answers_merged_with_plus_minus(self):
        # A LaTeX comma list is a set; with ± it used to come back nested ({{..}, {..}}), unreadable.
        assert parse_latex("1, 2", {}) == "{1, 2}"
        out = parse_latex(r"2 \pm \theta, -e", {})
        assert out == "{-e, 2 - theta, theta + 2}"
        assert len(parse_expression(out, parsing_params())) == 3

    @pytest.mark.parametrize(
        "latex",
        [
            "{" * 20 + "x" + "}" * 20,
            "(" * 100 + "x" + ")" * 100,
            "x^{" * 30 + "2" + "}" * 30,
            "}" * 20 + "{" * 20 + "x" + "}" * 20,  # stray closers used to hide the nesting after them
        ],
    )
    def test_deep_nesting_is_rejected_quickly(self, latex):
        # latex2sympy2_extended's parser is exponential in nesting depth: 20 nested { took ~40 s.
        import time

        start = time.monotonic()
        with pytest.raises(LatexParseError, match="nested"):
            parse_latex(latex, {})
        assert time.monotonic() - start < 1

    def test_ordinary_nesting_is_accepted(self):
        assert parse_latex(r"\left(\frac{\left(x+1\right)^{2}}{\left(x-1\right)^{3}}\right)^{\frac{1}{2}}", {})


@pytest.mark.parametrize(("digits", "allowed"), [(1000, True), (1001, False), (1003, False)])
def test_digit_limit_is_exact(digits, allowed):
    # The integer check estimated digits from bit_length, letting 1001-1002 digits through.
    config = parsing_params()
    if allowed:
        parse_expression("9" * digits, config)
    else:
        with pytest.raises(ExpressionParsingError, match="at most 1000"):
            parse_expression("1" + "0" * (digits - 1), config)


@pytest.mark.parametrize("response", ["10000000!", "factorial(10000000)", "100000!"])
def test_integer_functions_are_not_computed_while_parsing(response):
    # SymPy's evaluate=False skipped factorial and friends: 10000000! took minutes and 100000!
    # gave an integer too long to print.
    import time

    start = time.monotonic()
    parsed = parse_expression(response, parsing_params(elementary_functions=True))
    assert time.monotonic() - start < 2
    assert str(parsed).startswith("factorial(")


@pytest.mark.parametrize(
    ("response", "expected"),
    [("Pow(9,Pow(9,9))", "9**(9**9)"), ("Add(9**9**9,1)", "1 + 9**(9**9)")],
)
@pytest.mark.parametrize("strict", [True, False])
def test_operator_classes_are_not_computed_while_parsing(response, expected, strict):
    # Only function classes got evaluate=False: Pow(9, Pow(9, 9)) called by name never finished.
    import time

    start = time.monotonic()
    parsed = parse_expression(response, parsing_params(strict_syntax=strict))
    assert time.monotonic() - start < 2
    assert str(parsed) == expected


def test_latex_binomial_is_not_computed_while_parsing():
    # latex2sympy2_extended built \binom evaluated: this computed a 30-million-digit number.
    import time

    start = time.monotonic()
    assert parse_latex(r"\binom{100000000}{50000000}", {}) == "binomial(100000000, 50000000)"
    assert time.monotonic() - start < 2


class TestSimplifyIsBounded:
    """With simplify, parsing evaluates: 9**9**9 and factorial(10**8) never finished."""

    @pytest.mark.parametrize(
        "response",
        [
            "9**9**9",
            "Pow(9,Pow(9,9))",
            "factorial(100000000)",
            "(10**10)!",
            "(2*x)**100000",
            "catalan(10**6)",
            "harmonic(10**6)",
            "2**4000",
            "x = 9**9**9",
        ],
    )
    def test_huge_numbers_raise(self, response):
        import time

        start = time.monotonic()
        with pytest.raises(ExpressionParsingError, match="at most 1000"):
            parse_expression(response, parsing_params(simplify=True))
        assert time.monotonic() - start < 2

    def test_large_power_of_a_sum_raises(self):
        # simplify((x+1)**1000) took seconds, (x+1)**100000 never finished.
        with pytest.raises(ExpressionParsingError, match="at most 500"):
            parse_expression("(x+1)**100000", parsing_params(simplify=True))

    @pytest.mark.parametrize(
        ("response", "expected"),
        [
            ("2**3000", str(2**3000)),
            ("factorial(300)", str(math.factorial(300))),
            ("Mod(9**9**2, 7)", "1"),
            ("(x+1)**400", "(x + 1)**400"),
            ("x**(10**100)", f"x**{10**100}"),
            ("(x+1)**2 - x**2", "2*x + 1"),
            ("5!", "120"),
        ],
    )
    def test_reasonable_sizes_still_simplify(self, response, expected):
        assert str(parse_expression(response, parsing_params(simplify=True))) == expected
