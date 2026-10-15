"""Physical quantities: splitting a parsed response into value and unit, and converting it."""

from __future__ import annotations

import logging
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from typing import Any, NamedTuple

from sympy import Basic, Integer, simplify

from lambdafeedback.expression_parsing import (
    AbsoluteValueNotationError,
    BracketNotationError,
    ExpressionParsingError,
    SympyParsingConfig,
    parse_expression,
    parse_expressions,
    parse_latex,
    preprocess_expression,
    substitute,
    sympy_to_latex,
)
from lambdafeedback.slr_parsing import GROUP_LABEL, ExprNode, SLRError, SLRParser, TagHandler

from .data import CONVERSION_TO_BASE_SI, SI_BASE_UNITS, SI_PREFIXES, UNIT_SETS, units_in
from .errors import DisallowedUnitError, QuantityError, QuantityParseError, UnitConversionError
from .params import MAX_INPUT_LENGTH, QuantityParams
from .parser import Label, build_quantity_parser
from .tags import QuantityTag
from .text import called_names, disallowed_unit, mentions_celsius_or_fahrenheit, normalise_input

logger = logging.getLogger(__name__)

_BASE_UNIT_NAMES = frozenset(unit.name for unit in SI_BASE_UNITS)
_BASE_UNIT_DIMENSIONS = [(unit.name, unit.dimension) for unit in SI_BASE_UNITS]
_DIMENSION_NAMES = frozenset(unit.dimension for unit in SI_BASE_UNITS)
MAX_UNIT_EXPONENT = 100
"""Largest exponent a unit may have (``m^100``), of either sign."""

_EXPONENT_LABELS = frozenset({Label.NUMBER, GROUP_LABEL, Label.SOLIDUS, Label.PRODUCT, Label.SPACE})


def _exponent_problem(unit: ExprNode) -> str | None:
    """Why the exponents in a unit can't be used, if they can't.

    An exponent must be numbers combined with brackets, ``*``, ``/`` or spaces,
    and stay within :data:`MAX_UNIT_EXPONENT`. Otherwise converting the unit
    could build an enormous number: ``km^(10^10)`` has the factor
    ``1000^(10^10)``, and ``km^Pa^km`` (a unit as an exponent) hung.
    """
    stack = [unit]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.label != Label.POWER:
            continue
        bound = 1.0  # at least the exponent's magnitude: the product of its numbers' sizes
        exponent_nodes = [node.children[1]]
        while exponent_nodes:
            part = exponent_nodes.pop()
            if part.label not in _EXPONENT_LABELS:
                return f"A unit's exponent must be a number, not {part.original_string()!r}."
            if part.label == Label.NUMBER:
                bound *= max(1.0, abs(float(part.content)))
            exponent_nodes.extend(part.children)
        if bound > MAX_UNIT_EXPONENT:
            return f"The exponent of {node.original_string()!r} is too large; at most {MAX_UNIT_EXPONENT} is allowed."
    return None


def _has_stray_number(node: ExprNode) -> bool:
    """Whether a unit subtree contains a number outside an exponent or the ``1`` of ``1/unit``.

    Groups are not looked into: a bracketed group is kept whole (see
    :func:`_rotate_until_root_is_split`).
    """
    stack = [node]  # iterative: a long unit such as m*m*...*m is a deep tree
    while stack:
        node = stack.pop()
        if node.label == Label.NUMBER:
            return True
        if node.label == GROUP_LABEL:
            continue
        if node.label == Label.POWER:
            stack.append(node.children[0])
        elif node.label == Label.SOLIDUS and node.children[0].label == Label.NUMBER and node.children[0].content == "1":
            stack.append(node.children[1])
        else:
            stack.extend(node.children)
    return False


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


def _without_factor(dimension: Basic) -> Basic:
    """The dimension with its numeric factor removed: ``10**3*length/(3600*time)`` → ``length/time``."""
    factor = dimension.subs({symbol: 1 for symbol in dimension.free_symbols if str(symbol) in _DIMENSION_NAMES})
    return simplify(dimension / factor)


@cache
def _conversion_tree(parser: SLRParser, unit_name: str) -> ExprNode:
    """A unit's expansion in SI base units, parsed once per parser (callers copy it before changing it)."""
    tree: ExprNode = parser.parse(parser.scan(CONVERSION_TO_BASE_SI[unit_name]))[0]
    return tree


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


# ----------------------------------------------------------------------
# LaTeX for units: one renderer per node label (see _UNIT_LATEX)
# ----------------------------------------------------------------------


def _unit_latex(node: ExprNode) -> list[str]:
    """LaTeX for a unit subtree, as pieces to join."""
    render = _UNIT_LATEX.get(node.label, _plain_latex)
    return render(node)


def _braced_latex(node: ExprNode) -> list[str]:
    """LaTeX for a node already grouped by braces (a numerator, denominator or exponent): no brackets of its own."""
    while node.label == GROUP_LABEL and len(node.children) == 1:  # (x) or ((x)), not juxtaposition
        node = node.children[0]
    return _unit_latex(node)


def _plain_latex(node: ExprNode) -> list[str]:
    """A number, or any other node without a renderer of its own: its content."""
    return [node.content]


def _unit_name_latex(node: ExprNode) -> list[str]:
    return ["\\mathrm{", node.content, "}"]


def _product_latex(node: ExprNode) -> list[str]:
    left, right = node.children
    return [*_unit_latex(left), "\\cdot", *_unit_latex(right)]


def _space_latex(node: ExprNode) -> list[str]:
    left, right = node.children
    return [*_unit_latex(left), "~", *_unit_latex(right)]


def _power_latex(node: ExprNode) -> list[str]:
    base, exponent = node.children
    return [*_unit_latex(base), "^{", *_braced_latex(exponent), "}"]


def _solidus_latex(node: ExprNode) -> list[str]:
    numerator, denominator = node.children
    return ["\\frac{", *_braced_latex(numerator), "}{", *_braced_latex(denominator), "}"]


def _group_latex(node: ExprNode) -> list[str]:
    if node.delimiters is None:
        return _plain_latex(node)
    opening, closing = node.delimiters
    return [opening.content, *(part for child in node.children for part in _unit_latex(child)), closing.content]


_UNIT_LATEX: dict[str, Callable[[ExprNode], list[str]]] = {
    Label.UNIT: _unit_name_latex,
    Label.PRODUCT: _product_latex,
    Label.SPACE: _space_latex,
    Label.POWER: _power_latex,
    Label.SOLIDUS: _solidus_latex,
    GROUP_LABEL: _group_latex,
}


# ----------------------------------------------------------------------
# Reading a quantity: the steps of PhysicalQuantity.from_tree, in order
# ----------------------------------------------------------------------


def _parsing_config(params: QuantityParams) -> SympyParsingConfig:
    """The SymPy configuration for a quantity: unit, prefix and dimension names are positive and never split."""
    unsplittable = _unsplittable_names(params, all_forms=False)
    return SympyParsingConfig.from_params(
        params,
        unsplittable_symbols=unsplittable,
        symbol_assumptions=tuple((name, "positive") for name in unsplittable),
    )


def _rotate(root: ExprNode, right: bool, tag_handler: TagHandler) -> ExprNode:
    """Tree rotation at ``root``, to the right (the left child becomes the root) or to the left.

    Returns the new root.
    """
    # The child that becomes the root, and which of its children moves across to the old root.
    pivot, inner = (0, -1) if right else (1, 0)
    new_root = root.children[pivot]
    # Only binary nodes can be rotated; groups (one child) are atomic.
    if len(new_root.children) < 2:
        raise QuantityParseError(f"Cannot rotate {'right' if right else 'left'}.")
    root.children[pivot] = new_root.children[inner]
    new_root.children[inner] = root
    # Retagging can change the nodes too: in strict mode it strips the unit tag from a juxtaposition's children.
    root.tags = tag_handler(root)
    new_root.tags = tag_handler(new_root)
    return new_root


def _rotate_until_root_is_split(root: ExprNode, tag_handler: TagHandler) -> ExprNode:
    """Rotate ``SPACE`` roots until the root separates value (left) from unit (right); returns the new root.

    Only binary nodes are rotated into: a group (e.g. ``(2 m)``) is kept whole.
    A rotation followed by the opposite one would undo it, so a change of
    direction means there is no split (e.g. ``5 m/s x``, a unit between
    value parts).
    """
    previous: bool | None = None  # the direction of the last rotation (True: right)
    while root.label == Label.SPACE:
        left, right = root.children
        if QuantityTag.UNIT not in root.tags and len(right.children) > 1:
            rotate_right = False
        elif QuantityTag.UNIT in left.tags and len(left.children) > 1:
            rotate_right = True
        else:
            return root
        if previous is not None and rotate_right != previous:
            raise QuantityParseError(f"Cannot separate the value from the unit in {root.original!r}.")
        logger.debug("rotate %s to split value from unit", "right" if rotate_right else "left")
        root = _rotate(root, rotate_right, tag_handler)
        previous = rotate_right
    return root


def _split_value_and_unit(root: ExprNode, tag_handler: TagHandler) -> tuple[ExprNode, ExprNode | None, ExprNode | None]:
    """The root after rotating it to separate value from unit, the value and the unit.

    See :func:`_rotate_until_root_is_split`. Raises :class:`QuantityParseError` if
    they can't be separated, or the unit's exponents can't be used.
    """
    root = _rotate_until_root_is_split(root, tag_handler)
    value: ExprNode | None = None
    unit: ExprNode | None = None
    if (
        root.label == Label.SPACE
        and QuantityTag.UNIT not in root.children[0].tags
        and QuantityTag.UNIT in root.children[1].tags
    ):
        value, unit = root.children
    elif QuantityTag.UNIT in root.tags:
        unit = root
    else:
        value = root
    if logger.isEnabledFor(logging.DEBUG):
        value_text = None if value is None else value.content_string()
        unit_text = None if unit is None else unit.content_string()
        logger.debug("split %r into value %r and unit %r", root.original, value_text, unit_text)
    # e.g. "2 m 3 s" or "1 hour 30 minutes": the unit would contain a number.
    if unit is not None and _has_stray_number(unit):
        raise QuantityParseError(f"Cannot separate the value from the unit in {root.original!r}.")
    if unit is not None and (problem := _exponent_problem(unit)) is not None:
        raise QuantityParseError(problem)
    return root, value, unit


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


def _value_latex(value: ExprNode | None, params: QuantityParams) -> str | None:
    """LaTeX previewing the value (``None`` without one)."""
    if value is None:
        return None
    original = value.original_string()
    # Unit forms inside a called name (``s`` and ``in`` in ``sin(2)``) would split
    # the call in the preview, though the value itself is parsed as the call.
    calls = called_names(original)
    unit_forms = [
        form
        for form in _unsplittable_names(params, all_forms=True)
        if not any(form in call and form != call for call in calls)
    ]
    reserved = (*params.reserved_keywords, *unit_forms)
    preview_params = params.replace(reserved_keywords=reserved, rationalise=False)
    if preview_params.is_latex:
        # A LaTeX value is previewed as-is (as expression_parsing.preview_function used to).
        return original
    try:
        preprocessed = preprocess_expression(original, preview_params, name="response")
    except (BracketNotationError, AbsoluteValueNotationError) as exc:
        # Best-effort: preview with the guessed rewrite rather than failing outright.
        preprocessed = exc.expression
    parsed = parse_expressions(preprocessed, SympyParsingConfig.from_params(preview_params))
    settings = {"mul_symbol": r" \cdot "}
    if len(parsed) > 1:
        parts = sorted(sympy_to_latex(expr, preview_params.symbols, settings=settings) for expr in parsed)
        return "\\left\\{" + ",~".join(parts) + "\\right\\}"
    return sympy_to_latex(parsed[0], preview_params.symbols, settings=settings)


def _expand_units(node: ExprNode, parser: SLRParser) -> ExprNode:
    """Replace non-base units by their expression in SI base units (in place where possible)."""
    if node.label == Label.UNIT and not node.children and node.content not in _BASE_UNIT_NAMES:
        node = _conversion_tree(parser, node.content).copy()
    node.children = [_expand_units(child, parser) for child in node.children]
    return node


class _SympyForms(NamedTuple):
    standard_values: tuple[Basic, ...] | None
    standard_unit: Basic | None
    expanded_unit: Basic | None
    dimension: Basic
    base_dimension: Basic
    unit_factor: Basic


def _sympy_forms(
    name: str,
    value: ExprNode | None,
    unit: ExprNode | None,
    params: QuantityParams,
    config: SympyParsingConfig,
    parser: SLRParser,
) -> _SympyForms:
    """The SymPy forms: the standard value and unit, the expanded unit, dimensions and unit factor.

    Raises :class:`UnitConversionError` (naming ``name``) if the unit's expansion doesn't parse.
    """
    value_text: Any = value.content_string() if value is not None else None
    if value_text is not None and params.is_latex:
        value_text = parse_latex(value_text, params.symbols, params.simplify)
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
            value_text = f"({value_text})*({unit_factor})"
        dimension = parse_expression(substitute(expanded_unit_string, _BASE_UNIT_DIMENSIONS), config)
    return _SympyForms(
        standard_values=None if value_text is None else parse_expressions(value_text, config),
        standard_unit=standard_unit,
        expanded_unit=expanded_unit,
        dimension=dimension,
        base_dimension=_without_factor(dimension),
        unit_factor=unit_factor,
    )


# ----------------------------------------------------------------------
# The result
# ----------------------------------------------------------------------


@dataclass(frozen=True, eq=False, repr=False)
class PhysicalQuantity:
    """A response read as a quantity: its value and unit, their LaTeX, and SI forms.

    Use :func:`parse_quantity` to create one. SymPy results use the SI base
    units of :data:`~lambdafeedback.units.SI_BASE_UNITS` as symbols; mass is
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
        config = _parsing_config(params)
        root, value, unit = _split_value_and_unit(ast_root, parser.tag_handler)
        reverted_units = _revert_value_text(value) if value is not None else ()
        value_latex = _value_latex(value, params)
        unit_latex = "".join(_unit_latex(unit)) if unit is not None else None
        separator = "~" if value_latex is not None and unit_latex is not None else ""
        forms = _sympy_forms(name, value, unit, params, config, parser)
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
