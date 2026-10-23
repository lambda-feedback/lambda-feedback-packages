"""Reading the precision a number was written to (from compareExpressions#273 and #277)."""

import pytest

from lambdafeedback.expression_parsing import (
    WrittenNumber,
    read_written_number,
    round_to_decimal_places,
    round_to_significant_figures,
)


@pytest.mark.parametrize(
    ("string", "expected"),
    [
        ("92.00", WrittenNumber("92", "00", True)),
        ("92", WrittenNumber("92", "", False)),
        ("0.0032", WrittenNumber("0", "0032", True)),
        ("540", WrittenNumber("540", "", False)),
        ("540.", WrittenNumber("540", "", True)),
        (".5", WrittenNumber("", "5", True)),
        ("-3.14", WrittenNumber("3", "14", True)),
        ("+3.14", WrittenNumber("3", "14", True)),
        (" 3.14 ", WrittenNumber("3", "14", True)),
        ("007", WrittenNumber("007", "", False)),
        ("5.02e4", WrittenNumber("5", "02", True, 4)),
        ("5.02E+4", WrittenNumber("5", "02", True, 4)),
        ("5e-3", WrittenNumber("5", "", False, -3)),
        ("5.02*10^4", WrittenNumber("5", "02", True, 4)),
        ("5.02*10**-4", WrittenNumber("5", "02", True, -4)),
        ("0", WrittenNumber("0", "", False)),
    ],
)
def test_reads_a_written_number(string, expected):
    assert read_written_number(string) == expected


@pytest.mark.parametrize("string", ["", "two", ".", "-", "--3.14", "3.14e", "3.14e-", "3.1.4", "3x", "1/2", "3.14 m"])
def test_rejects_anything_else(string):
    assert read_written_number(string) is None


@pytest.mark.parametrize(
    ("string", "expected"),
    [
        ("92.00", 4),
        ("92", 2),
        ("0.0032", 2),
        ("540", 2),
        ("540.", 3),
        ("0", 1),
        ("0.00", 1),
        ("007", 1),
        ("5.02e4", 3),
        ("-3.14", 3),
    ],
)
def test_significant_figures(string, expected):
    assert read_written_number(string).significant_figures == expected


@pytest.mark.parametrize(
    ("string", "expected"),
    [
        ("3.14", 2),
        ("3.140", 3),
        ("92.00", 2),
        ("0.0032", 4),
        ("540", 0),
        ("540.", 0),
        ("0", 0),
        ("5.02e4", 0),
        ("5e-3", 3),
        ("1.5e-3", 4),
        ("1.5*10^-3", 4),
    ],
)
def test_decimal_places(string, expected):
    assert read_written_number(string).decimal_places == expected


@pytest.mark.parametrize(
    ("value", "figures", "expected"),
    [
        (0, 3, 0.0),
        (3.14159, 3, 3.14),
        (3.14159, 6, 3.14159),
        (540, 2, 540.0),
        (0.0032, 2, 0.0032),
        (50200, 3, 50200.0),
        (-3.14159, 3, -3.14),
    ],
)
def test_round_to_significant_figures(value, figures, expected):
    assert round_to_significant_figures(value, figures) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("value", "places", "expected"),
    [
        (0, 2, "0.00"),
        (92, 2, "92.00"),
        (3.14159, 2, "3.14"),
        (3.14159, 4, "3.1416"),
        (3.146, 2, "3.15"),
        (2.7, 0, "3"),
        (-3.14159, 2, "-3.14"),
    ],
)
def test_round_to_decimal_places(value, places, expected):
    assert round_to_decimal_places(value, places) == expected
