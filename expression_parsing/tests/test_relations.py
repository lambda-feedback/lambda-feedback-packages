"""Relations in a response: equations, inequalities and ``!=`` (from compareExpressions#276)."""

import pytest
from sympy import And, Equality, GreaterThan, LessThan, Ne, StrictGreaterThan, StrictLessThan, Symbol

from lambdafeedback.expression_parsing import (
    ExpressionParams,
    ExpressionParsingError,
    LatexParseError,
    SympyParsingConfig,
    parse_expression,
    parse_latex,
    preprocess_expression,
    split_relations,
)

x = Symbol("x")


def parse(expr, **params):
    expression_params = ExpressionParams.from_dict({"elementary_functions": True, **params})
    preprocessed = preprocess_expression(expr, expression_params)
    return parse_expression(preprocessed, SympyParsingConfig.from_params(expression_params))


@pytest.mark.parametrize(
    ("expr", "expected_type"),
    [
        ("x > 5", StrictGreaterThan),
        ("x < 5", StrictLessThan),
        ("x >= 5", GreaterThan),
        ("x <= 5", LessThan),
        ("5 < x", StrictLessThan),
        ("2*x - 10 >= 0", GreaterThan),
        ("2x - 10 > 0", StrictGreaterThan),
        ("x>=5", GreaterThan),
        ("x ≤ 5", LessThan),
        ("x ≥ 5", GreaterThan),
    ],
)
def test_inequality(expr, expected_type):
    assert isinstance(parse(expr), expected_type)


@pytest.mark.parametrize(
    ("expr", "part_types"),
    [
        ("1 < x < 5", (StrictLessThan, StrictLessThan)),
        ("1 <= x <= 5", (LessThan, LessThan)),
        ("5 >= x >= 1", (GreaterThan, GreaterThan)),
        ("5 >= x > 1", (GreaterThan, StrictGreaterThan)),
        ("0 < x - 1 <= 4", (StrictLessThan, LessThan)),
    ],
)
def test_chained_inequality_is_both_relations(expr, part_types):
    parsed = parse(expr)
    assert isinstance(parsed, And)
    assert len(parsed.args) == 2
    assert {type(arg) for arg in parsed.args} == set(part_types)


@pytest.mark.parametrize("expr", ["x != 5", "5 != x", "x - 5 != 0", "x ≠ 5", "x!=5"])
def test_not_equal(expr):
    # `!=` was read as factorial and `=`: `x != 5` was Eq(factorial(x), 5).
    assert isinstance(parse(expr), Ne)


@pytest.mark.parametrize("expr", ["x = 5", "2*x**2 = 10*y**2 + 14"])
def test_equation_is_still_an_equality(expr):
    assert isinstance(parse(expr), Equality)


def test_operands_are_left_unevaluated_unless_simplifying():
    assert parse("x < 2 + 3").rhs != 5
    assert parse("x < 2 + 3", simplify=True).rhs == 5


@pytest.mark.parametrize(
    ("expr", "message"),
    [
        ("1 < x > 5", "point one way"),
        ("a < b > c", "point one way"),
        ("1 <= x <= y <= 5", "two inequalities"),
        ("a < b < c < d", "two inequalities"),
        ("x != y != 5", "can't be combined"),
        ("1 < x != 5", "can't be combined"),
        ("x < y = 5", "can't be combined"),
        ("x = y < 5", "can't be combined"),
        ("x = y != 5", "can't be combined"),
        ("x <", "on each side"),
        ("< 5", "on each side"),
        ("x = = y", "on each side"),
        ("x = y =", "on each side"),
    ],
)
def test_rejected(expr, message):
    with pytest.raises(ExpressionParsingError, match=message):
        parse(expr)


@pytest.mark.parametrize("expr", ["x = y = z", "x=y=z"])
def test_chained_equality_is_each_equation(expr):
    # From compareExpressions#278: more than one "=" used to be rejected.
    y, z = Symbol("y"), Symbol("z")
    assert parse(expr) == And(Equality(x, y), Equality(y, z))


def test_long_chained_equality():
    parsed = parse("a = b = c = d")
    assert isinstance(parsed, And)
    assert len(parsed.args) == 3
    assert all(isinstance(arg, Equality) for arg in parsed.args)


def test_latex_chained_equality_parses_through():
    y, z = Symbol("y"), Symbol("z")
    assert parse(parse_latex("x = y = z", {})) == And(Equality(x, y), Equality(y, z))


def test_latex_empty_side_is_rejected():
    with pytest.raises(LatexParseError, match="on each side"):
        parse_latex("x = = y", {})


def test_split_relations():
    assert split_relations("1 < x <= 5", ExpressionParsingError) == (["1 ", " x ", " 5"], ["<", "<="])
    assert split_relations("x + 1", ExpressionParsingError) == (["x + 1"], [])


def test_latex_inequality_parses_through():
    # parse_latex writes the relation as text, which parse_expression then reads.
    assert parse(parse_latex(r"x \leq 5", {})) == LessThan(x, 5)
