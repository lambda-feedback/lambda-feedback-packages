"""The string scanners that replaced regular expressions, on the edge cases each regex handled."""

import pytest

from lambdafeedback.expression_parsing import (
    compute_relative_tolerance_from_significant_decimals,
    generate_arbitrary_number_pattern_matcher,
    is_complex_number_on_cartesian_form,
    is_complex_number_on_exponential_form,
    is_number,
)
from lambdafeedback.expression_parsing.latex import _protect_e_symbols, _replace_command, extract_latex, parse_latex
from lambdafeedback.expression_parsing.substitution import normalise_unicode_operators


@pytest.mark.parametrize(
    ("string", "expected"),
    [
        ("0", True),
        ("-12.5", True),
        (".5", True),
        ("1.", False),
        ("012", False),
        ("-", False),
        ("1e-3", True),
        ("1 E5", True),
        ("2*10^3", True),
        ("2*10**-3", True),
        ("1e", False),
        ("1e05", False),
        ("1*10^", False),
    ],
)
def test_is_number(string, expected):
    assert is_number(string) is expected


@pytest.mark.parametrize(
    ("string", "expected"),
    [("1+2*I", True), ("-1.5", True), ("I", True), ("2I", True), ("+", False), ("", False), ("1+-2*I", True)],
)
def test_cartesian_form(string, expected):
    assert is_complex_number_on_cartesian_form(string) is expected


@pytest.mark.parametrize(
    ("string", "expected"),
    [
        ("2*exp(3*I)", True),
        ("E^(I)", True),
        ("2E**(-1.5*I)", True),
        ("E^I", True),
        # The I is required.
        ("E^", False),
        ("2*exp(3)", False),
        ("E**2", False),
    ],
)
def test_exponential_form(string, expected):
    assert is_complex_number_on_exponential_form(string) is expected


@pytest.mark.parametrize(
    ("pattern", "string", "expected"),
    [
        ("2x+3", "10x+0.5", True),
        ("2x+3", "x+3", False),
        ("x+(-2)", "x+(5)", True),
        ("x+(-2)", "x+5", True),
        ("-2", "-7", True),
        ("-2", "7", False),
        ("a [b]", "a[b]", True),
        ("x^2", "x ^ 1e3", True),
    ],
)
def test_number_pattern_matcher(pattern, string, expected):
    assert generate_arbitrary_number_pattern_matcher(pattern)(string) is expected


@pytest.mark.parametrize(("string", "expected"), [("1.234", 5e-4), ("12 *10^3", 0.05), ("-0.0012e5", 0.05), ("x", 0)])
def test_relative_tolerance(string, expected):
    assert compute_relative_tolerance_from_significant_decimals(string) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("$$x$", "x"),
        ("a \\(y\\) $z$", "y"),
        ("$\nx$y$", "y"),
        ("no math", "no math"),
        ("$unclosed", "$unclosed"),
    ],
)
def test_extract_latex_edge_cases(symbol, expected):
    assert extract_latex(symbol) == expected


def test_preprocess_e_keeps_scientific_notation_and_other_commands():
    latex, replacements = _protect_e_symbols("2e5 + e + \\exp{x} + 1.e-3 + \\gamma")
    assert set(replacements) == {"e", "\\gamma"}
    gamma = replacements["\\gamma"]
    assert latex == f"2E5 + {replacements['e']} + \\exp{{x}} + 1.E-3 + {gamma}"


def test_pm_command_swallows_spaces_but_is_not_the_start_of_pmod():
    assert _replace_command("a\\pmod b \\pm  c\\pm", "\\pm", "P") == "a\\pmod b Pc" + "P"
    assert parse_latex("a \\pm  b", {}) == parse_latex("a\\pm b", {})


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ("x²", "x**(2)"),
        ("x^²", "x**(2)"),
        ("x ** ²", "x **(2)"),
        ("x  ²", "x**(2)"),
        ("x ^ ²", "x **(2)"),
        ("x***²", "x***(2)"),
        ("x⁻¹ + y²³", "x**(-1) + y**(23)"),
    ],
)
def test_superscripts(expr, expected):
    assert normalise_unicode_operators(expr) == expected


@pytest.mark.parametrize(
    "string, signed, expected",
    [
        ("12x", False, 2),
        (".5e-3 m", False, 5),
        ("-1.5", False, None),
        ("-1.5", True, 4),
        ("2 e3", False, 1),  # no spaces before the exponent
        ("2E3", False, 1),  # only "e"
        ("x", True, None),
    ],
)
def test_plain_number_end(string, signed, expected):
    from lambdafeedback.expression_parsing import plain_number_end

    assert plain_number_end(string, signed=signed) == expected
