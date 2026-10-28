"""The string scanners that replaced regular expressions, on the edge cases each regex handled."""

import pytest

from lambdafeedback.physical_quantities import QuantityParams
from lambdafeedback.physical_quantities.parser import _number_prefix
from lambdafeedback.physical_quantities.preprocessing import transform_prefixes_to_standard
from lambdafeedback.physical_quantities.text import (
    called_names,
    collapse_whitespace,
    mentions_celsius_or_fahrenheit,
    normalise_latex,
)


@pytest.mark.parametrize(
    ("string", "expected"),
    [
        ("12 m", "12"),
        ("-1.5e-3x", "-1.5e-3"),
        (".5", ".5"),
        ("007", "0"),
        ("1.", "1"),
        ("1e", "1"),
        ("1e05", "1e0"),
        ("-", None),
        ("m", None),
    ],
)
def test_number_prefix(string, expected):
    assert _number_prefix(string) == expected


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ("20 ℃", True),
        ("20°C", True),
        ("20 ° F", True),
        ("20 deg C", True),
        ("20 degrees F", True),
        ("20 degreeC", True),
        ("20 °Cd", False),
        ("20 xdeg C", False),
        ("20 deg", False),
        ("20 C", False),
    ],
)
def test_celsius_or_fahrenheit(expr, expected):
    assert mentions_celsius_or_fahrenheit(expr) is expected


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ("2~\\mathrm{m}", "2 m"),
        ("2\\,\\text{kg}\\;\\textrm{s}", "2 kg s"),
        ("2\\quad m\\qquad s", "2  m  s"),
        ("\\quadrant", "\\quadrant"),
        ("\\\\~", "\\\\ "),
        ("\\mathrm{a{b}}", "\\mathrm{a{b}}"),
        ("\\operatorname{m}^2", "m^2"),
    ],
)
def test_normalise_latex(expr, expected):
    assert normalise_latex(expr) == expected


def test_called_names():
    assert called_names("sin (2) + 9log(x) + é(y) + _f(z) + (w)") == ["sin", "log", "_f"]


@pytest.mark.parametrize(("text", "expected"), [("a \t b", "a b"), (" a\n", " a "), ("\t", " "), ("", "")])
def test_collapse_whitespace(text, expected):
    assert collapse_whitespace(text) == expected


@pytest.mark.parametrize(
    ("expr", "expected"),
    [("5 μs", "5 micros"), ("5 μ  s", "5 micros"), ("xμs", "xμs"), ("5 deka m", "5 decam"), ("5 μ", "5 μ")],
)
def test_transform_prefixes_to_standard(expr, expected):
    assert transform_prefixes_to_standard(expr) == expected


def test_units_string_splits_on_spaces_and_commas():
    params = QuantityParams.from_dict({"units_string": " SI, common\timperial ,"})
    assert params.unit_sets == frozenset({"SI", "common", "imperial"})
