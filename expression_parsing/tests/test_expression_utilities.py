import pytest
from sympy import Symbol, sqrt

from lambdafeedback.expression_parsing import (
    AbsoluteValueNotationError,
    BracketNotationError,
    ExpressionParams,
    FunctionName,
    SymbolSpec,
    compute_relative_tolerance_from_significant_decimals,
    convert_absolute_notation,
    convert_bracket_notation,
    create_expression_set,
    extract_latex,
    find_matching_parenthesis,
    has_matching_brackets,
    is_multiple_answers_wrapper,
    latex_symbols,
    normalise_unicode_operators,
    preprocess_expression,
    substitute,
    substitute_input_symbols,
    substitutions_sort_key,
    sympy_symbols,
    sympy_to_latex,
)
from lambdafeedback.expression_parsing.substitution import (
    elementary_function_substitutions,
    greek_symbol_substitutions,
)


class TestConvertUnicodeDashes:
    @pytest.mark.parametrize(
        "expr, expected",
        [
            # No dashes at all
            ("x+y", "x+y"),
            # ASCII hyphen-minus is unchanged
            ("x-y", "x-y"),
            ("", ""),
            # HYPHEN, NON-BREAKING HYPHEN, FIGURE DASH, EN DASH, EM DASH, MINUS SIGN,
            # SMALL HYPHEN-MINUS, FULLWIDTH HYPHEN-MINUS
            *((f"x{dash}y", "x-y") for dash in "‐‑‒–—−﹣－"),
            # Several different dashes, and repeats
            ("x–y−z", "x-y-z"),
            ("x−y−z", "x-y-z"),
        ],
    )
    def test_convert_unicode_dashes(self, expr, expected):
        assert normalise_unicode_operators(expr) == expected


class TestConvertAbsoluteNotation:
    @pytest.mark.parametrize(
        "expr, expected_expr",
        [
            # No pipes — unchanged
            ("x+y", "x+y"),
            # Exactly two pipes — simple conversion
            ("|x|", "Abs(x)"),
            ("|x+y|", "Abs(x+y)"),
            # Two non-adjacent absolute values
            ("|x|+|y|", "Abs(x)+Abs(y)"),
        ],
    )
    def test_convert_absolute_notation(self, expr, expected_expr):
        assert convert_absolute_notation(expr, name="response") == expected_expr

    def test_ambiguous_pipes_raise(self):
        # More than 2 pipes with ambiguous positions raises, carrying the guess and the name.
        with pytest.raises(AbsoluteValueNotationError) as info:
            convert_absolute_notation("|x|y|z|", name="response")
        assert info.value.expression == "Abs(x)y*Abs(z)"
        assert info.value.name == "response"


class TestTransformUnicodeGreekSymbols:
    def test_no_greek_symbols_returns_empty(self):
        assert greek_symbol_substitutions("x + y") == []

    def test_named_greek_symbol_returns_self_substitution(self):
        result = greek_symbol_substitutions("alpha + 1")
        assert ("alpha", " alpha ") in result

    def test_unicode_greek_alias_maps_to_name(self):
        # α is an alias for "alpha"
        result = greek_symbol_substitutions("α")
        assert ("α", " alpha ") in result

    def test_multiple_greek_symbols(self):
        result = greek_symbol_substitutions("alpha + beta")
        assert ("alpha", " alpha ") in result
        assert ("beta", " beta ") in result

    def test_unicode_beta_alias(self):
        result = greek_symbol_substitutions("β")
        assert ("β", " beta ") in result


class TestProtectElementaryFunctionsSubstitutions:
    def test_no_functions_returns_empty(self):
        assert elementary_function_substitutions("x + y") == []

    def test_sin_generates_self_substitution(self):
        result = elementary_function_substitutions("sin(x)")
        assert ("sin", " sin ") in result

    def test_alias_maps_to_canonical_name(self):
        # arctan is an alias for atan
        result = elementary_function_substitutions("arctan(x)")
        assert ("arctan", " atan ") in result

    def test_multiple_functions(self):
        result = elementary_function_substitutions("sin(x) + cos(x)")
        assert ("sin", " sin ") in result
        assert ("cos", " cos ") in result


class TestSubstituteInputSymbols:
    def test_plain_expression_unchanged(self):
        assert substitute_input_symbols("x+y", ExpressionParams()) == "x+y"

    def test_lambda_replaced_with_lamda(self):
        assert substitute_input_symbols("lambda", ExpressionParams()) == "lamda"

    def test_alias_replaced_with_symbol_code(self):
        params = {"symbols": {"x": {"latex": r"\(x\)", "aliases": ["x_var"]}}}
        assert substitute_input_symbols("x_var", ExpressionParams.from_dict(params)) == "x"

    def test_symbol_code_preserved(self):
        params = {"symbols": {"x": {"latex": r"\(x\)", "aliases": ["x_var"]}}}
        assert substitute_input_symbols("x", ExpressionParams.from_dict(params)) == "x"


class TestFindMatchingParenthesis:
    @pytest.mark.parametrize(
        "string, index, delimiters, expected",
        [
            # Simple pair
            ("(x)", 0, None, 2),
            # Longer content
            ("(x+y)", 0, None, 4),
            # Nested — outer pair
            ("((x+y))", 0, None, 6),
            # Nested — inner pair
            ("((x+y))", 1, None, 5),
            # No closing delimiter
            ("(x", 0, None, -1),
            # Custom square-bracket delimiters
            ("[x+y]", 0, ("[", "]"), 4),
            # Starts mid-string
            ("a(b+c)d", 1, None, 5),
        ],
    )
    def test_find_matching_parenthesis(self, string, index, delimiters, expected):
        if delimiters is None:
            result = find_matching_parenthesis(string, index)
        else:
            result = find_matching_parenthesis(string, index, delimiters)
        assert result == expected


class TestHasMatchingBrackets:
    @pytest.mark.parametrize(
        "expr, expected",
        [
            ("x+y", True),
            ("(x+y)", True),
            ("[x+y]", True),
            ("{x+y}", True),
            ("[x+(y-1)]", True),
            ("{(x+1), (x-1)}", True),
            # Mismatched bracket types
            ("[x+y)", False),
            ("(x+y]", False),
            ("{x+y)", False),
            ("[(x+y]", False),
            # Unbalanced brackets
            ("[x+y", False),
            ("x+y]", False),
            ("((x+y)", False),
        ],
    )
    def test_has_matching_brackets(self, expr, expected):
        assert has_matching_brackets(expr) is expected


class TestConvertBracketNotation:
    @pytest.mark.parametrize(
        "expr, expected",
        [
            ("[x+y]", "(x+y)"),
            ("[x+(y-1)]", "(x+(y-1))"),
            ("{x+1}*{x-2}", "(x+1)*(x-2)"),
        ],
    )
    def test_matched_brackets_are_converted(self, expr, expected):
        assert convert_bracket_notation(expr) == expected

    def test_multiple_answers_wrapper_left_untouched(self):
        assert convert_bracket_notation("{x+1, x-1}") == "{x+1, x-1}"

    @pytest.mark.parametrize(
        "expr, guess",
        [
            # Wrong bracket *kind* — the guess collapses the distinction and parses fine.
            ("[x+y)", "(x+y)"),
            ("(x+y]", "(x+y)"),
            ("{x+y)", "(x+y)"),
            # Genuinely unbalanced — the guess still doesn't balance.
            ("[x+y", "(x+y"),
            ("x+y]", "x+y)"),
        ],
    )
    def test_mismatched_brackets_raise_with_a_best_guess(self, expr, guess):
        with pytest.raises(BracketNotationError) as info:
            convert_bracket_notation(expr)
        assert info.value.expression == guess


class TestSubstitute:
    @pytest.mark.parametrize(
        "string, substitutions, expected",
        [
            # Empty substitutions — unchanged
            ("hello", [], "hello"),
            # Single substitution
            ("hello world", [("world", "earth")], "hello earth"),
            # Whole string replaced
            ("abc", [("abc", "xyz")], "xyz"),
            # No match — unchanged
            ("hello", [("world", "earth")], "hello"),
            # Earlier substitution in list wins at the same position
            ("abc", [("a", "p"), ("ab", "q")], "pbc"),
            # Longer substitution listed first wins
            ("abc", [("ab", "q"), ("a", "p")], "qc"),
            # Multiple non-overlapping substitutions
            ("a b c", [("a", "x"), ("b", "y"), ("c", "z")], "x y z"),
        ],
    )
    def test_substitute(self, string, substitutions, expected):
        assert substitute(string, substitutions) == expected

    @pytest.mark.parametrize(
        "string, expected",
        [("sin(x)", " sin (x)"), ("sin (x)", " sin  (x)"), ("sin^2(x)", " sin ^2(x)"), ("sinx", "sinx")],
    )
    def test_function_name_only_matches_where_applied(self, string, expected):
        assert substitute(string, [(FunctionName("sin"), " sin ")]) == expected


class TestComputeRelativeTolerance:
    @pytest.mark.parametrize(
        "string, expected",
        [
            # Non-numeric → 0
            ("not_a_number", 0),
            # 1 sig char, below DEFAULT_SIGNIFICANT_FIGURES=2 floor → 5e-2
            ("1", 5e-2),
            # "0.5" → chars "05" → lstrip "5" → len 1 → floor applies → 5e-2
            ("0.5", 5e-2),
            # "1.5" → chars "15" → len 2 → max(2,2)=2 → 5e-2
            ("1.5", 5e-2),
            # "100" → chars "100" (lstrip removes nothing, '1' stops it) → len 3 → 5e-3
            ("100", 5e-3),
            # "1.23" → chars "123" (decimal removed) → len 3 → 5e-3
            ("1.23", 5e-3),
            # Scientific notation: mantissa "1.23" → len 3 → 5e-3
            ("1.23e5", 5e-3),
            # Negative: "-1.23" → lstrip removes "-" → "123" → len 3 → 5e-3
            ("-1.23", 5e-3),
        ],
    )
    def test_relative_tolerance(self, string, expected):
        result = compute_relative_tolerance_from_significant_decimals(string)
        assert result == pytest.approx(expected)


class TestSympySymbols:
    def test_returns_symbol_objects(self):
        result = sympy_symbols({"x": {}, "y": {}})
        assert result == {"x": Symbol("x"), "y": Symbol("y")}

    def test_empty_dict(self):
        assert sympy_symbols({}) == {}

    def test_symbol_names_preserved(self):
        result = sympy_symbols({"alpha": {}})
        assert result["alpha"] == Symbol("alpha")


class TestExtractLatex:
    @pytest.mark.parametrize(
        "symbol, expected",
        [
            # LaTeX delimiters removed
            (r"\(x^2\)", "x^2"),
            ("$x^2$", "x^2"),
            ("$$x^2$$", "x^2"),
            (r"\(\alpha\)", r"\alpha"),
            # No delimiters — returned as-is
            ("x^2", "x^2"),
            ("plain", "plain"),
        ],
    )
    def test_extract_latex(self, symbol, expected):
        assert extract_latex(symbol) == expected


class TestLatexSymbols:
    def test_maps_symbol_to_latex_string(self):
        syms = {"x": SymbolSpec(r"\(x\)")}
        result = latex_symbols(syms)
        assert result == {Symbol("x"): "x"}

    def test_greek_latex_preserved(self):
        syms = {"alpha": SymbolSpec(r"\(\alpha\)")}
        result = latex_symbols(syms)
        assert result == {Symbol("alpha"): r"\alpha"}

    def test_empty_dict(self):
        assert latex_symbols({}) == {}


class TestSympyToLatex:
    def test_simple_power(self):
        expr = Symbol("x") ** 2
        syms = {"x": SymbolSpec(r"\(x\)")}
        result = sympy_to_latex(expr, syms)
        assert result == "x^{2}"

    def test_custom_latex_name_used(self):
        expr = Symbol("alpha")
        syms = {"alpha": SymbolSpec(r"\(\alpha\)")}
        result = sympy_to_latex(expr, syms)
        assert result == r"\alpha"

    def test_sqrt(self):
        expr = sqrt(Symbol("x"))
        syms = {"x": SymbolSpec(r"\(x\)")}
        result = sympy_to_latex(expr, syms)
        assert result == r"\sqrt{x}"


class TestSubstitutionsSortKey:
    def test_longer_left_element_sorts_first(self):
        long_sub = ("abc", "p")
        short_sub = ("ab", "p")
        assert substitutions_sort_key(long_sub) < substitutions_sort_key(short_sub)

    def test_equal_left_length_longer_right_sorts_first(self):
        long_right = ("ab", "pqr")
        short_right = ("ab", "p")
        assert substitutions_sort_key(long_right) < substitutions_sort_key(short_right)

    def test_sort_orders_longer_substitutions_first(self):
        subs = [("a", "x"), ("abc", "y"), ("ab", "z")]
        subs.sort(key=substitutions_sort_key)
        assert subs[0][0] == "abc"
        assert subs[1][0] == "ab"
        assert subs[2][0] == "a"


class TestCreateExpressionSet:
    def test_plain_string_wrapped_in_list(self):
        result = create_expression_set("x+y", ExpressionParams())
        assert result == ["x+y"]

    def test_set_notation_split_into_list(self):
        result = create_expression_set("{x, y}", ExpressionParams())
        assert sorted(result) == ["x", "y"]

    def test_list_input_accepted(self):
        result = create_expression_set(["x", "y"], ExpressionParams())
        assert sorted(result) == ["x", "y"]

    def test_plus_minus_expands_to_two_expressions(self):
        params = {"plus_minus": "±"}
        result = create_expression_set("±x", ExpressionParams.from_dict(params))
        assert sorted(result) == sorted(["+x", "-x"]) or sorted(result) == sorted(["x", "-x"])
        assert len(result) == 2

    def test_curly_braces_used_for_grouping_are_not_split(self):
        result = create_expression_set("{x+1}*{x-2}", ExpressionParams())
        assert result == ["{x+1}*{x-2}"]


class TestIsMultipleAnswersWrapper:
    @pytest.mark.parametrize(
        "expr, expected",
        [
            ("{x, y}", True),
            ("{x+1}", True),
            ("{(x+1), (x-1)}", True),
            ("x+y", False),
            ("{x+1}*{x-2}", False),
            ("{x+1}*x", False),
        ],
    )
    def test_is_multiple_answers_wrapper(self, expr, expected):
        assert is_multiple_answers_wrapper(expr) is expected


class TestPreprocessExpression:
    def test_plain_expression_succeeds(self):
        assert preprocess_expression("x+y", ExpressionParams(), name="response") == "x+y"

    def test_absolute_value_notation_converted(self):
        assert preprocess_expression("|x|", ExpressionParams(), name="response") == "Abs(x)"

    def test_ambiguous_pipes_raise(self):
        with pytest.raises(AbsoluteValueNotationError) as info:
            preprocess_expression("|x|y|z|", ExpressionParams(), name="response")
        assert info.value.name == "response"

    def test_square_brackets_converted(self):
        assert preprocess_expression("[x+y]", ExpressionParams(), name="response") == "(x+y)"

    @pytest.mark.parametrize(
        "expr, guess",
        [
            # Wrong bracket kind — the guess parses fine.
            ("[x+y)", "(x+y)"),
            ("(x+y]", "(x+y)"),
            ("{x+y)", "(x+y)"),
            # Genuinely unbalanced — the guess still doesn't balance.
            ("[x+y", "(x+y"),
            ("x+y]", "x+y)"),
        ],
    )
    def test_mismatched_brackets_raise_with_a_best_guess(self, expr, guess):
        with pytest.raises(BracketNotationError) as info:
            preprocess_expression(expr, ExpressionParams(), name="response")
        assert info.value.expression == guess

    def test_bracket_mismatch_takes_precedence_over_absolute_value_ambiguity(self):
        # Bracket error surfaces, but its guess still has the absolute-value guess applied.
        with pytest.raises(BracketNotationError) as info:
            preprocess_expression("[x|y|z)", ExpressionParams(), name="response")
        assert info.value.expression == "(xAbs(y)z)"
