"""SymPy-based expression parsing and preprocessing.

Typical use::

    params = ExpressionParams.from_dict(evaluation_params)
    expr = preprocess_expression(response, params, name="response")
    parsed = parse_expression(expr, SympyParsingConfig.from_params(params))
    latex = sympy_to_latex(parsed, params.symbols)

Extracted from compareExpressions: previewing a response and mapping
failures to learner-facing feedback text are app-layer concerns and live in
compareExpressions, not here. Failures are raised as typed exceptions (see
:mod:`.errors`); the recoverable ones (:class:`BracketNotationError`,
:class:`AbsoluteValueNotationError`) carry a best-guess rewrite as
``.expression``, for a caller that wants to continue with the guess.
"""

import logging
from importlib.metadata import PackageNotFoundError, version

from ._safe_parse import MAX_INPUT_LENGTH, MAX_NUMBER_DIGITS, MAX_NUMBER_EXPONENT, MAX_SIMPLIFY_POWER
from ._scanning import find_matching_parenthesis
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
from .latex import MAX_LATEX_NESTING, extract_latex, latex_symbols, parse_latex, sanitise_latex, sympy_to_latex
from .numbers import (
    compute_relative_tolerance_from_significant_decimals,
    generate_arbitrary_number_pattern_matcher,
    is_complex_number_on_cartesian_form,
    is_complex_number_on_exponential_form,
    is_number,
    plain_number_end,
)
from .params import Convention, ExpressionParams, SymbolSpec, parse_symbol_assumptions
from .preprocessing import (
    convert_absolute_notation,
    convert_bracket_notation,
    create_expression_set,
    has_matching_brackets,
    is_multiple_answers_wrapper,
    preprocess_expression,
)
from .substitution import (
    FunctionName,
    normalise_unicode_operators,
    substitute,
    substitute_input_symbols,
    substitutions_sort_key,
)
from .symbol_tables import UNICODE_OPERATORS
from .sympy_parsing import SympyParsingConfig, parse_expression, parse_expressions, sympy_symbols

# Library convention: callers decide where log records go (``logging.basicConfig(level=logging.DEBUG)`` shows them).
logging.getLogger(__name__).addHandler(logging.NullHandler())

try:
    __version__ = version("lambdafeedback-expression-parsing")
except PackageNotFoundError:  # running from a source checkout that isn't installed
    __version__ = "0+unknown"

__all__ = [
    "MAX_INPUT_LENGTH",
    "MAX_LATEX_NESTING",
    "MAX_NUMBER_DIGITS",
    "MAX_NUMBER_EXPONENT",
    "MAX_SIMPLIFY_POWER",
    "UNICODE_OPERATORS",
    "AbsoluteValueNotationError",
    "BracketNotationError",
    "Convention",
    "ExpressionParams",
    "ExpressionParsingError",
    "FunctionName",
    "InvalidParameterError",
    "LatexParseError",
    "SymbolAssumptionError",
    "SymbolSpec",
    "SympyParsingConfig",
    "UnknownConventionError",
    "__version__",
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
    "parse_expressions",
    "parse_latex",
    "parse_symbol_assumptions",
    "plain_number_end",
    "preprocess_expression",
    "sanitise_latex",
    "substitute",
    "substitute_input_symbols",
    "substitutions_sort_key",
    "sympy_symbols",
    "sympy_to_latex",
]
