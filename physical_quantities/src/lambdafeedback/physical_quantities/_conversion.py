"""Converting a quantity to SI base units: its SymPy forms, dimension and unit factor."""

from __future__ import annotations

from functools import cache
from typing import Any, NamedTuple

from sympy import Basic, Integer, simplify

from lambdafeedback.expression_parsing import (
    SympyParsingConfig,
    create_expression_set,
    parse_expression,
    parse_expressions,
    parse_latex,
    substitute,
)
from lambdafeedback.slr_parsing import ExprNode, SLRParser

from .data import CONVERSION_TO_BASE_SI, SI_BASE_UNITS, unsplittable_names
from .errors import UnitConversionError
from .params import QuantityParams
from .parser import Label

_BASE_UNIT_NAMES = frozenset(unit.name for unit in SI_BASE_UNITS)

_BASE_UNIT_DIMENSIONS = [(unit.name, unit.dimension) for unit in SI_BASE_UNITS]

_DIMENSION_NAMES = frozenset(unit.dimension for unit in SI_BASE_UNITS)


def _without_factor(dimension: Basic) -> Basic:
    """The dimension with its numeric factor removed: ``10**3*length/(3600*time)`` → ``length/time``."""
    factor = dimension.subs({symbol: 1 for symbol in dimension.free_symbols if str(symbol) in _DIMENSION_NAMES})
    return simplify(dimension / factor)


@cache
def _conversion_tree(parser: SLRParser, unit_name: str) -> ExprNode:
    """A unit's expansion in SI base units, parsed once per parser (callers copy it before changing it)."""
    tree: ExprNode = parser.parse(parser.scan(CONVERSION_TO_BASE_SI[unit_name]))[0]
    return tree


def quantity_parsing_config(params: QuantityParams) -> SympyParsingConfig:
    """The SymPy configuration for a quantity: unit, prefix and dimension names are positive and never split."""
    unsplittable = unsplittable_names(params.unit_sets, all_forms=False)
    return SympyParsingConfig.from_params(
        params,
        unsplittable_symbols=unsplittable,
        symbol_assumptions=tuple((name, "positive") for name in unsplittable),
    )


def _expand_units(node: ExprNode, parser: SLRParser) -> ExprNode:
    """Replace non-base units by their expression in SI base units (in place where possible)."""
    if node.label == Label.UNIT and not node.children and node.content not in _BASE_UNIT_NAMES:
        node = _conversion_tree(parser, node.content).copy()
    node.children = [_expand_units(child, parser) for child in node.children]
    return node


class SympyForms(NamedTuple):
    """The SymPy fields of a :class:`~lambdafeedback.physical_quantities.PhysicalQuantity`."""

    standard_values: tuple[Basic, ...] | None
    standard_unit: Basic | None
    expanded_unit: Basic | None
    dimension: Basic
    base_dimension: Basic
    unit_factor: Basic


def sympy_forms(
    name: str,
    value: ExprNode | None,
    unit: ExprNode | None,
    params: QuantityParams,
    config: SympyParsingConfig,
    parser: SLRParser,
) -> SympyForms:
    """The SymPy forms: the standard value and unit, the expanded unit, dimensions and unit factor.

    Raises :class:`UnitConversionError` (naming ``name``) if the unit's expansion doesn't parse.
    """
    value_text: Any = value.content_string() if value is not None else None
    if value_text is not None and params.is_latex:
        value_text = parse_latex(value_text, params.symbols, params.simplify)
    standard_values: tuple[Basic, ...] | None = None
    standard_unit: Any = None
    expanded_unit: Any = None
    dimension: Basic = Integer(1)
    unit_factor: Basic = Integer(1)
    if unit is not None:
        expanded_unit_string = _expand_units(unit.copy(), parser).content_string()
        try:
            expanded_unit = standard_unit = parse_expression(expanded_unit_string, config)
        except Exception as e:  # SymPy raises many types; all mean the expansion didn't parse
            raise UnitConversionError(f"SymPy was unable to parse the {name} unit") from e
        if value is not None:
            base_symbols = {symbol: 1 for symbol in standard_unit.free_symbols if str(symbol) in _BASE_UNIT_NAMES}
            unit_factor = standard_unit.subs(base_symbols).simplify()
            standard_unit = (standard_unit / unit_factor).simplify(rational=True)
            if len(create_expression_set(value_text, config.substitution_params)) > 1:
                # A list ({1, 2}, 1,2 in LaTeX, or ±): the factor applies to each value, not to the list.
                factored_values = tuple(value * unit_factor for value in parse_expressions(value_text, config))
                standard_values = tuple(dict.fromkeys(factored_values))
            else:
                value_text = f"({value_text})*({unit_factor})"
        dimension = parse_expression(substitute(expanded_unit_string, _BASE_UNIT_DIMENSIONS), config)
    if standard_values is None and value_text is not None:
        standard_values = parse_expressions(value_text, config)
    return SympyForms(
        standard_values=standard_values,
        standard_unit=standard_unit,
        expanded_unit=expanded_unit,
        dimension=dimension,
        base_dimension=_without_factor(dimension),
        unit_factor=unit_factor,
    )
