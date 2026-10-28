"""Physical quantities: the result of reading a response as a value and a unit, and how it is read.

:meth:`PhysicalQuantity.from_tree` runs the steps in order: splitting the
parse tree into value and unit (``_split``), restoring the value's text
(here), LaTeX (``_latex``) and the SymPy forms in SI base units
(``_conversion``).
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from typing import Any

from sympy import Basic, simplify

from lambdafeedback.expression_parsing import ExpressionParsingError, SympyParsingConfig
from lambdafeedback.slr_parsing import GROUP_LABEL, ExprNode, SLRError, SLRParser

from ._conversion import quantity_parsing_config, sympy_forms
from ._latex import latex_for_unit, latex_for_value
from ._split import split_value_and_unit
from .data import UNIT_SETS
from .errors import DisallowedUnitError, QuantityError, QuantityParseError
from .params import MAX_INPUT_LENGTH, QuantityParams
from .parser import Label, build_quantity_parser
from .tags import QuantityTag
from .text import disallowed_unit, mentions_celsius_or_fahrenheit, normalise_input

logger = logging.getLogger(__name__)


def _content(node: ExprNode) -> Any:
    return node.content


def _subtree_texts(root: ExprNode) -> dict[int, str]:
    """Each node's ``content_string()`` (by ``id``), computed bottom-up in one pass."""
    order = []
    stack = [root]
    while stack:  # pre-order: every node before its descendants
        node = stack.pop()
        order.append(node)
        stack.extend(node.children)
    texts: dict[int, str] = {}
    for node in reversed(order):  # so each node's children are done first
        texts[id(node)] = "".join(
            part if is_output else texts[id(part)] for is_output, part in node.traverse_step(node, _content)
        )
    return texts


@dataclass(frozen=True)
class RevertedUnit:
    """Unit-like text found inside a value, restored to what was typed.

    ``before``, ``marked`` and ``after`` are the text surrounding and
    covering the unit-like span, e.g. for ``"2 kg + 3"``:
    ``before="2 ", marked="kg", after=" + 3"``.
    """

    before: str
    marked: str
    after: str


def _revert_value_text(value: ExprNode) -> tuple[RevertedUnit, ...]:
    """Restore the value's text as written; returns its unit-like parts (parents first).

    The value's nodes get their typed text back as their content, in place:
    the tree was just parsed, and nothing else holds it. A unit-like node's
    marked text is its restored content around its children's text from
    before restoring (computed once, bottom-up, by :func:`_subtree_texts`,
    rather than per node, which was quadratic).
    """
    texts = _subtree_texts(value)
    reverted = []
    for node in value.walk():
        if node.label != GROUP_LABEL:
            node.content = node.original[node.start : node.end + 1]
        if node.label == Label.UNIT or QuantityTag.UNIT in node.tags:
            marked = "".join(
                part if is_output else texts[id(part)] for is_output, part in node.traverse_step(node, _content)
            )
            reverted.append(
                RevertedUnit(before=node.original[: node.start], marked=marked, after=node.original[node.end + 1 :])
            )
    return tuple(reverted)


@dataclass(frozen=True, eq=False, repr=False)
class PhysicalQuantity:
    """A response read as a quantity: its value and unit, their LaTeX, and SI forms.

    Use :func:`parse_quantity` to create one. SymPy results use the SI base
    units of :data:`~lambdafeedback.physical_quantities.SI_BASE_UNITS` as symbols; mass is
    in grams (``kilogram`` expands to ``1000*gram``).

    Its attributes can't be set (it is frozen), but ``value``, ``unit`` and
    ``ast_root`` are ordinary parse trees. Quantities compare by identity.

    Attributes:
        value, unit: the value and unit subtrees (either may be ``None``).
        ast_root: the whole parse tree.
        reverted_units: :class:`RevertedUnit` facts for unit-like text read
            as part of the value.
        value_latex, unit_latex, latex: LaTeX for the value, the unit, and both.
        standard_values: the value with the unit's factor applied (SymPy), as a
            tuple: one expression, or several for a value such as ``{1, 2}``.
        standard_unit: the unit in SI base units without its factor.
        expanded_unit: the unit in SI base units.
        dimension: the unit's dimension, keeping the unit's factor (``km/h``
            gives ``10**3*length/(3600*time)``), ``1`` without a unit.
        base_dimension: the dimension without the factor (``length/time``);
            see :func:`same_dimension`.
        unit_factor: the numeric factor between the unit and SI base units.
        parsing_config: the SymPy parsing configuration used.
    """

    name: str
    params: QuantityParams
    ast_root: ExprNode
    parsing_config: SympyParsingConfig
    value: ExprNode | None
    unit: ExprNode | None
    reverted_units: tuple[RevertedUnit, ...]
    value_latex: str | None
    unit_latex: str | None
    latex: str
    standard_values: tuple[Basic, ...] | None
    standard_unit: Basic | None
    expanded_unit: Basic | None
    dimension: Basic
    base_dimension: Basic
    unit_factor: Basic

    @classmethod
    def from_tree(cls, name: str, params: QuantityParams, ast_root: ExprNode, parser: SLRParser) -> PhysicalQuantity:
        """Read a quantity from its parse tree (built by ``parser``, the quantity parser for ``params``).

        :func:`parse_quantity` parses the text and calls this. ``ast_root`` is
        rotated and its value's text restored in place.
        """
        config = quantity_parsing_config(params)
        root, value, unit = split_value_and_unit(ast_root, parser.tag_handler)
        reverted_units = _revert_value_text(value) if value is not None else ()
        value_latex = latex_for_value(value, params)
        unit_latex = latex_for_unit(unit) if unit is not None else None
        separator = "~" if value_latex is not None and unit_latex is not None else ""
        forms = sympy_forms(name, value, unit, params, config, parser)
        return cls(
            name=name,
            params=params,
            ast_root=root,
            parsing_config=config,
            value=value,
            unit=unit,
            reverted_units=reverted_units,
            value_latex=value_latex,
            unit_latex=unit_latex,
            latex=(value_latex or "") + separator + (unit_latex or ""),
            standard_values=forms.standard_values,
            standard_unit=forms.standard_unit,
            expanded_unit=forms.expanded_unit,
            dimension=forms.dimension,
            base_dimension=forms.base_dimension,
            unit_factor=forms.unit_factor,
        )

    @property
    def parser(self) -> SLRParser:
        """Deprecated (removed in 1.0): the quantity parser for ``params``; use :func:`build_quantity_parser`."""
        warnings.warn(
            "PhysicalQuantity.parser is deprecated and will be removed in 1.0; "
            "use build_quantity_parser(params.unit_sets, params.strictness) instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return build_quantity_parser(self.params.unit_sets, self.params.strictness)

    def __repr__(self) -> str:
        value = None if self.value is None else self.value.content_string()
        unit = None if self.unit is None else self.unit.content_string()
        return f"PhysicalQuantity(value={value!r}, unit={unit!r})"


def parse_quantity(expr: str, params: QuantityParams, name: str = "response") -> PhysicalQuantity:
    """Read ``expr`` as a physical quantity (value and/or unit).

    ``name`` (e.g. ``"response"``) identifies the quantity in messages.
    ``·``, ``⋅`` and ``×`` are read as ``*``. Alternative prefix spellings
    (``μ``, ``deka``) need :func:`preprocess_quantity` first. With
    ``params.is_latex``, LaTeX spacing and ``\\mathrm{...}``/``\\text{...}``
    are read as plain spaces and text, so ``2~\\mathrm{m}`` is ``2 m``.

    Raises :class:`QuantityParseError` if ``expr`` can't be read as a
    quantity (including a value SymPy can't parse, a number inside the unit,
    a temperature in degrees Celsius or Fahrenheit, or input longer than
    :data:`MAX_INPUT_LENGTH`), :class:`DisallowedUnitError` (a
    :class:`QuantityParseError`) if it spells out a unit from a unit set not in
    ``params.unit_sets`` (``10 litre`` with only ``SI``), or
    :class:`UnitConversionError` if its unit can't be converted to SI base
    units. Both are :class:`QuantityError`\\ s carrying ``expression`` and ``name``.
    """
    if len(expr) > MAX_INPUT_LENGTH:
        raise QuantityParseError(
            f"The {name} is too long: {len(expr)} characters; at most {MAX_INPUT_LENGTH} are allowed.",
            expression=expr,
            name=name,
        )
    if mentions_celsius_or_fahrenheit(expr):
        raise QuantityParseError(
            "Temperatures in degrees Celsius or Fahrenheit aren't supported; use kelvin.", expression=expr, name=name
        )
    # Any whitespace (tabs, newlines, no-break and thin spaces) as one space; drop zero-width characters.
    text = normalise_input(expr, latex=params.is_latex)
    logger.debug("parse_quantity %r: normalised to %r", expr, text)
    if (disallowed := disallowed_unit(text, params.unit_sets)) is not None:
        word, unit = disallowed
        logger.debug("parse_quantity %r: %r is a unit outside %s", expr, word, sorted(params.unit_sets))
        sets = tuple(set_name for set_name, units in UNIT_SETS.items() if unit in units)
        raise DisallowedUnitError(
            f"{word!r} is a unit ({unit.name}) from the {' or '.join(sets)} unit set, which isn't allowed here.",
            unit=unit.name,
            unit_sets=sets,
            expression=expr,
            name=name,
        )
    parser = build_quantity_parser(params.unit_sets, params.strictness)
    try:
        roots = parser.parse(parser.scan(text.strip()))
        if len(roots) > 1:
            raise QuantityParseError("Parsed quantity does not have a single root.")
        return PhysicalQuantity.from_tree(name, params, roots[0], parser)
    except QuantityError as exc:
        if exc.expression is None:
            exc.expression = expr
        if exc.name is None:
            exc.name = name
        raise
    except SLRError as exc:
        raise QuantityParseError(str(exc), expression=expr, name=name) from exc
    except ExpressionParsingError as exc:
        raise QuantityParseError(f"Could not read the {name}'s value: {exc}", expression=expr, name=name) from exc
    except RecursionError as exc:
        # Thousands of operators (m*m*...*m) nest deeper than the recursive steps (here and in SymPy) allow.
        raise QuantityParseError(f"The {name} is too long or too deeply nested.", expression=expr, name=name) from exc


def same_dimension(first: PhysicalQuantity, second: PhysicalQuantity) -> bool:
    """Whether two quantities have the same dimension, whatever their units' factors.

    ``5 km/h`` and ``3 m/s`` have the same dimension (``length/time``); so do
    ``1 L`` and ``1 m^3``. Quantities without units are dimensionless, as are
    angles (``2 deg`` has the same dimension as ``2``).
    """
    return bool(simplify(first.base_dimension - second.base_dimension) == 0)
