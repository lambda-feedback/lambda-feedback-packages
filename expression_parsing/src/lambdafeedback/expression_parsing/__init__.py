"""SymPy-based expression parsing and preprocessing.

Typical use::

    params = ExpressionParams.from_dict(evaluation_params)
    expr = preprocess_expression("response", response, params)
    parsed = parse_expression(expr, SympyParsingConfig.from_params(params))
    latex = sympy_to_latex(parsed, params.symbols)

Extracted from compareExpressions: previewing a response and mapping
failures to learner-facing feedback text are app-layer concerns and live in
compareExpressions, not here. Failures are raised as typed exceptions (see
:mod:`.errors`); the recoverable ones (:class:`BracketNotationError`,
:class:`AbsoluteValueNotationError`) carry a best-guess rewrite as
``.expression``, for a caller that wants to continue with the guess.
"""

from .conventions import apply_convention, convention_parser
from .errors import (
    AbsoluteValueNotationError,
    BracketNotationError,
    ExpressionParsingError,
    InvalidParameterError,
    LatexParseError,
    SymbolAssumptionError,
    UnknownConventionError,
)
from .latex import extract_latex, latex_symbols, parse_latex, sanitise_latex, sympy_to_latex
from .numbers import (
    compute_relative_tolerance_from_significant_decimals,
    generate_arbitrary_number_pattern_matcher,
    is_complex_number_on_cartesian_form,
    is_complex_number_on_exponential_form,
    is_number,
)
from .params import Convention, ExpressionParams, SymbolSpec, parse_symbol_assumptions
from .preprocessing import (
    convert_absolute_notation,
    convert_bracket_notation,
    create_expression_set,
    find_matching_parenthesis,
    has_matching_brackets,
    is_multiple_answers_wrapper,
    preprocess_expression,
)
from .substitution import normalise_unicode_operators, substitute, substitute_input_symbols, substitutions_sort_key
from .sympy_parsing import SympyParsingConfig, parse_expression, sympy_symbols

__all__ = [
    "AbsoluteValueNotationError",
    "BracketNotationError",
    "Convention",
    "ExpressionParams",
    "ExpressionParsingError",
    "InvalidParameterError",
    "LatexParseError",
    "SymbolAssumptionError",
    "SymbolSpec",
    "SympyParsingConfig",
    "UnknownConventionError",
    "apply_convention",
    "compute_relative_tolerance_from_significant_decimals",
    "convention_parser",
    "convert_absolute_notation",
    "convert_bracket_notation",
    "create_expression_set",
    "extract_latex",
    "find_matching_parenthesis",
    "generate_arbitrary_number_pattern_matcher",
    "has_matching_brackets",
    "is_complex_number_on_cartesian_form",
    "is_complex_number_on_exponential_form",
    "is_multiple_answers_wrapper",
    "is_number",
    "latex_symbols",
    "normalise_unicode_operators",
    "parse_expression",
    "parse_latex",
    "parse_symbol_assumptions",
    "preprocess_expression",
    "sanitise_latex",
    "substitute",
    "substitute_input_symbols",
    "substitutions_sort_key",
    "sympy_symbols",
    "sympy_to_latex",
]
