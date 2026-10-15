"""LaTeX for a quantity: a preview of its value, and its unit (one renderer per node label)."""

from __future__ import annotations

from collections.abc import Callable

from lambdafeedback.expression_parsing import (
    AbsoluteValueNotationError,
    BracketNotationError,
    SympyParsingConfig,
    parse_expressions,
    preprocess_expression,
    sympy_to_latex,
)
from lambdafeedback.slr_parsing import GROUP_LABEL, ExprNode

from .data import unsplittable_names
from .params import QuantityParams
from .parser import Label
from .text import called_names


def latex_for_unit(unit: ExprNode) -> str:
    """LaTeX for a unit subtree: ``\\mathrm{}`` names, ``\\cdot`` products, fractions and powers."""
    return "".join(_unit_latex(unit))


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


def latex_for_value(value: ExprNode | None, params: QuantityParams) -> str | None:
    """LaTeX previewing the value (``None`` without one): the value as SymPy reads it, unit forms kept whole."""
    if value is None:
        return None
    original = value.original_string()
    # Unit forms inside a called name (``s`` and ``in`` in ``sin(2)``) would split
    # the call in the preview, though the value itself is parsed as the call.
    calls = called_names(original)
    unit_forms = [
        form
        for form in unsplittable_names(params.unit_sets, all_forms=True)
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
