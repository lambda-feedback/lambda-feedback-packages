"""Physical quantities: splitting a parsed response into value and unit, and converting it."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sympy import Basic

from lambdafeedback.expression_parsing import (
    AbsoluteValueNotationError,
    BracketNotationError,
    ExpressionParsingError,
    SympyParsingConfig,
    parse_expression,
    parse_latex,
    preprocess_expression,
    substitute,
    sympy_to_latex,
)
from lambdafeedback.slr_parsing import ExprNode, SLRError, SLRParser

from .data import CONVERSION_TO_BASE_SI, SI_BASE_UNITS, SI_PREFIXES, units_in
from .errors import QuantityError, QuantityParseError, UnitConversionError
from .params import QuantityParams
from .parser import build_quantity_parser
from .tags import QuantityTag

_BASE_UNIT_NAMES = frozenset(unit.name for unit in SI_BASE_UNITS)
_BASE_UNIT_DIMENSIONS = [(unit.name, unit.dimension) for unit in SI_BASE_UNITS]
_CALL = re.compile(r"([A-Za-z_]\w*)\s*\(")
"""A name followed by ``(``: a function call."""


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


def _unsplittable_names(params: QuantityParams, all_forms: bool) -> list[str]:
    """Names that must not be split into letters: prefixes, units, and dimension names.

    ``all_forms`` adds unit symbols, alternative spellings and plurals (used
    for the value's preview) to the unit names (used for parsing).
    """
    names = {prefix.name for prefix in SI_PREFIXES} | _BASE_UNIT_NAMES
    names |= {unit.dimension for unit in SI_BASE_UNITS}
    for unit in units_in(params.unit_sets):
        names |= {unit.name, unit.symbol, *unit.alternatives, *unit.plurals} if all_forms else {unit.name}
    return sorted(names)


class PhysicalQuantity:
    """A response read as a quantity: its value and unit, their LaTeX, and SI forms.

    Use :func:`parse_quantity` to create one. SymPy results use the SI base
    units of :data:`~lambdafeedback.units.SI_BASE_UNITS` as symbols; mass is
    in grams (``kilogram`` expands to ``1000*gram``).

    Attributes:
        value, unit: the value and unit subtrees (either may be ``None``).
        ast_root: the whole parse tree.
        reverted_units: :class:`RevertedUnit` facts for unit-like text read
            as part of the value.
        value_latex, unit_latex, latex: LaTeX for the value, the unit, and both.
        standard_value: the value with the unit's factor applied (SymPy), or a
            set of them for a value such as ``{1, 2}``.
        standard_unit: the unit in SI base units without its factor.
        expanded_unit: the unit in SI base units.
        dimension: the unit's dimension (e.g. ``length/time``), ``1`` without a unit.
        unit_factor: the numeric factor between the unit and SI base units.
        parsing_config: the SymPy parsing configuration used.
    """

    name: str
    params: QuantityParams
    ast_root: ExprNode
    parser: SLRParser
    parsing_config: SympyParsingConfig
    reverted_units: list[RevertedUnit]
    value: ExprNode | None
    unit: ExprNode | None
    value_latex: str | None
    unit_latex: str | None
    latex: str
    standard_value: Basic | set[Basic] | None
    standard_unit: Basic | None
    expanded_unit: Basic | None
    dimension: Basic
    unit_factor: Basic

    def __init__(self, name: str, params: QuantityParams, ast_root: ExprNode, parser: SLRParser) -> None:
        self.name = name
        self.params = params
        self.ast_root = ast_root
        self.parser = parser
        unsplittable = _unsplittable_names(params, all_forms=False)
        self.parsing_config = SympyParsingConfig.from_params(
            params,
            unsplittable_symbols=unsplittable,
            symbol_assumptions=tuple((name, "positive") for name in unsplittable),
        )
        self.reverted_units = []
        self.value = None
        self.unit = None

        self._split_value_and_unit()
        if self.value is not None:
            self.value.traverse(self._revert_content)
        self.value_latex = self._value_latex()
        self.unit_latex = "".join(self._unit_latex(self.unit)) if self.unit is not None else None
        separator = "~" if self.value_latex is not None and self.unit_latex is not None else ""
        self.latex = (self.value_latex or "") + separator + (self.unit_latex or "")
        (
            self.standard_value,
            self.standard_unit,
            self.expanded_unit,
            self.dimension,
            self.unit_factor,
        ) = self._all_forms()

    def __repr__(self) -> str:
        value = None if self.value is None else self.value.content_string()
        unit = None if self.unit is None else self.unit.content_string()
        return f"PhysicalQuantity(value={value!r}, unit={unit!r})"

    # ------------------------------------------------------------------
    # Splitting value and unit
    # ------------------------------------------------------------------

    def _rotate(self, direction: int) -> None:
        """Tree rotation at the root: ``direction`` 1 rotates right, 0 left."""
        old_root = self.ast_root
        new_root = old_root.children[1 - direction]
        # Only binary nodes can be rotated; groups (one child) are atomic.
        if len(new_root.children) < 2:
            raise QuantityParseError(f"Cannot rotate {'right' if direction == 1 else 'left'}.")
        old_root.children[1 - direction] = new_root.children[-direction]
        new_root.children[-direction] = old_root
        old_root.tags = self.parser.tag_handler(old_root)
        new_root.tags = self.parser.tag_handler(new_root)
        self.ast_root = new_root

    def _rotate_until_root_is_split(self) -> None:
        """Rotate ``SPACE`` roots until the root separates value (left) from unit (right).

        Only binary nodes are rotated into: a group (e.g. ``(2 m)``) is kept whole.
        A rotation followed by the opposite one would undo it, so a change of
        direction means there is no split (e.g. ``5 m/s x``, a unit between
        value parts).
        """
        previous = None
        while self.ast_root.label == "SPACE":
            left, right = self.ast_root.children
            if QuantityTag.UNIT not in self.ast_root.tags and len(right.children) > 1:
                direction = 0
            elif QuantityTag.UNIT in left.tags and len(left.children) > 1:
                direction = 1
            else:
                return
            if previous is not None and direction != previous:
                raise QuantityParseError(f"Cannot separate the value from the unit in {self.ast_root.original!r}.")
            self._rotate(direction)
            previous = direction

    def _split_value_and_unit(self) -> None:
        self._rotate_until_root_is_split()
        root = self.ast_root
        if (
            root.label == "SPACE"
            and QuantityTag.UNIT not in root.children[0].tags
            and QuantityTag.UNIT in root.children[1].tags
        ):
            self.value, self.unit = root.children
        elif QuantityTag.UNIT in root.tags:
            self.unit = root
        else:
            self.value = root

    def _revert_content(self, node: ExprNode) -> list[str]:
        """Traversal action restoring the value's text as written, noting unit-like parts."""
        if node.label != "GROUP":
            node.content = node.original[node.start : node.end + 1]
        if node.label == "UNIT" or QuantityTag.UNIT in node.tags:
            self.reverted_units.append(
                RevertedUnit(
                    before=node.original[: node.start],
                    marked=node.content_string(),
                    after=node.original[node.end + 1 :],
                )
            )
        return ["", ""]

    # ------------------------------------------------------------------
    # LaTeX
    # ------------------------------------------------------------------

    def _value_latex(self) -> str | None:
        if self.value is None:
            return None
        original = self.value.original_string()
        # Unit forms inside a called name (``s`` and ``in`` in ``sin(2)``) would split
        # the call in the preview, though the value itself is parsed as the call.
        calls = _CALL.findall(original)
        unit_forms = [
            form
            for form in _unsplittable_names(self.params, all_forms=True)
            if not any(form in call and form != call for call in calls)
        ]
        reserved = (*self.params.reserved_keywords, *unit_forms)
        params = self.params.replace(reserved_keywords=reserved, rationalise=False)
        if params.is_latex:
            # A LaTeX value is previewed as-is (as expression_parsing.preview_function used to).
            return original
        try:
            preprocessed = preprocess_expression("response", original, params)
        except (BracketNotationError, AbsoluteValueNotationError) as exc:
            # Best-effort: preview with the guessed rewrite rather than failing outright.
            preprocessed = exc.expression
        parsed = parse_expression(preprocessed, SympyParsingConfig.from_params(params))
        settings = {"mul_symbol": r" \cdot "}
        if isinstance(parsed, set):
            parts = sorted(sympy_to_latex(expr, params.symbols, settings=settings) for expr in parsed)
            return "\\left\\{" + ",~".join(parts) + "\\right\\}"
        return sympy_to_latex(parsed, params.symbols, settings=settings)

    def _unit_latex(self, node: ExprNode) -> list[str]:
        # TODO: skip unnecessary parentheses (e.g. groups inside powers and fractions)
        children = node.children
        if node.label == "PRODUCT":
            return [*self._unit_latex(children[0]), "\\cdot", *self._unit_latex(children[1])]
        if node.label == "SPACE":
            return [*self._unit_latex(children[0]), "~", *self._unit_latex(children[1])]
        if node.label == "UNIT":
            return ["\\mathrm{", node.content, "}"]
        if node.label == "GROUP":
            return [node.content[0], *(part for child in children for part in self._unit_latex(child)), node.content[1]]
        if node.label == "POWER":
            return [*self._unit_latex(children[0]), "^{", *self._unit_latex(children[1]), "}"]
        if node.label == "SOLIDUS":
            return ["\\frac{", *self._unit_latex(children[0]), "}{", *self._unit_latex(children[1]), "}"]
        return [node.content]  # NUMBER and anything else

    # ------------------------------------------------------------------
    # Conversion to SI base units
    # ------------------------------------------------------------------

    def _expand_units(self, node: ExprNode) -> ExprNode:
        """Replace non-base units by their expression in SI base units (in place where possible)."""
        if node.label == "UNIT" and not node.children and node.content not in _BASE_UNIT_NAMES:
            node = self.parser.parse(self.parser.scan(CONVERSION_TO_BASE_SI[node.content]))[0]
        node.children = [self._expand_units(child) for child in node.children]
        return node

    def _all_forms(self) -> tuple[Basic | set[Basic] | None, Basic | None, Basic | None, Basic, Basic]:
        config = self.parsing_config
        value: Any = self.value.content_string() if self.value is not None else None
        if value is not None and self.params.is_latex:
            value = parse_latex(value, self.params.symbols, self.params.simplify)
        unit: Any = None
        expanded_unit: Any = None
        dimension = parse_expression("1", config)
        unit_factor = parse_expression("1", config)
        if self.unit is not None:
            expanded_unit_string = self._expand_units(self.unit.copy()).content_string()
            try:
                expanded_unit = unit = parse_expression(expanded_unit_string, config)
            except Exception as e:
                raise UnitConversionError(f"SymPy was unable to parse the {self.name} unit") from e
            if self.value is not None:
                base_symbols = {symbol: 1 for symbol in unit.free_symbols if str(symbol) in _BASE_UNIT_NAMES}
                unit_factor = unit.subs(base_symbols).simplify()
                unit = (unit / unit_factor).simplify(rational=True)
                value = f"({value})*({unit_factor})"
            dimension = parse_expression(substitute(expanded_unit_string, _BASE_UNIT_DIMENSIONS), config)
        if value is not None:
            value = parse_expression(value, config)
        return value, unit, expanded_unit, dimension, unit_factor


def parse_quantity(expr: str, params: QuantityParams, name: str = "response") -> PhysicalQuantity:
    """Read ``expr`` as a physical quantity (value and/or unit).

    ``name`` (e.g. ``"response"``) identifies the quantity in messages.

    Raises :class:`QuantityParseError` if ``expr`` can't be read as a
    quantity (including a value SymPy can't parse), or
    :class:`UnitConversionError` if its unit can't be converted to SI base
    units. Both are :class:`QuantityError`\\ s carrying ``expression`` and ``name``.
    """
    parser = build_quantity_parser(params.unit_sets, params.strictness)
    try:
        roots = parser.parse(parser.scan(expr.strip()))
        if len(roots) > 1:
            raise QuantityParseError("Parsed quantity does not have a single root.")
        return PhysicalQuantity(name, params, roots[0], parser)
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
