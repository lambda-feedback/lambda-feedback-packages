"""Parsing preprocessed expressions into SymPy objects."""

from __future__ import annotations

import logging
import warnings
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import cached_property
from io import StringIO
from keyword import iskeyword
from token import NAME, OP
from tokenize import TokenError, generate_tokens
from typing import Any

import sympy
from sympy import Basic, Chi, E, Equality, Function, I, Lambda, Set, Sum, Symbol, Tuple, beta, gamma, zeta
from sympy.parsing.sympy_parser import (
    _token_splittable,
    auto_number,
    auto_symbol,
    convert_equals_signs,
    convert_xor,
    factorial_notation,
    function_exponentiation,
    implicit_multiplication,
    lambda_notation,
    rationalize,
    repeated_decimals,
    split_symbols_custom,
)
from sympy.utilities.exceptions import SymPyDeprecationWarning

from ._safe_parse import MATH_NAMESPACE, TOO_DEEP_MESSAGE, check_evaluation_cost, check_input_length, safe_parse_expr
from .conventions import apply_convention
from .errors import ExpressionParsingError, SymbolAssumptionError
from .params import ExpressionParams
from .preprocessing import convert_bracket_notation, create_expression_set, split_equation
from .substitution import (
    Substitution,
    elementary_function_substitutions,
    greek_symbol_substitutions,
    sorted_substitutions,
    substitute,
)
from .symbol_tables import EMBEDDABLE_FUNCTION_NAMES

logger = logging.getLogger(__name__)

_APPLIED = ("(", "**", "^")


def _following(values: Sequence[str], index: int) -> str:
    """The token text after ``values[index]`` (``""`` at the end)."""
    return values[index + 1] if index + 1 < len(values) else ""


def _reads_as_letters(name: str, following: str, defined: Mapping[str, Any]) -> bool:
    """True for a short function spelling (``re``, ``max``) not applied to anything and not a defined name."""
    return name not in defined and name.casefold() in EMBEDDABLE_FUNCTION_NAMES and following not in _APPLIED


def _keywords_as_names(tokens: list[Any], local_dict: dict[str, Any], global_dict: Any) -> list[Any]:
    """Read Python keywords, and short function names not applied to anything, as ordinary names.

    Python's grammar would reject a keyword (``in``, ``is``, ``as``, ``del``,
    ...), so each becomes the ``Symbol('in')`` (``Function('in')`` before a
    bracket) that ``auto_symbol`` makes of any other unknown name: without
    strict syntax it is then split like any other word. A keyword that is a
    defined name (a task symbol with code ``in``) is rebound to an identifier
    so it keeps its own object.

    A name in :data:`EMBEDDABLE_FUNCTION_NAMES` (``re``, ``sign``, ``max``,
    ...) is only that function when followed by ``(``, ``**`` or ``^``;
    otherwise it is letters too, like the ``re`` in ``area``.
    """
    result: list[Any] = []
    values = [value for _, value in tokens]
    for index, (kind, value) in enumerate(tokens):
        following = _following(values, index)
        if kind != NAME or not (iskeyword(value) or _reads_as_letters(value, following, local_dict)):
            result.append((kind, value))
        elif value in local_dict:
            alias = f"{value}__keyword"
            local_dict[alias] = local_dict[value]
            result.append((NAME, alias))
        else:
            constructor = "Function" if following == "(" else "Symbol"
            result += [(NAME, constructor), (OP, "("), (NAME, repr(value)), (OP, ")")]
    return result


def sympy_symbols(symbols: Iterable[str]) -> dict[str, Symbol]:
    """``{name: Symbol(name)}`` for use as ``parse_expr``'s ``local_dict``."""
    return {name: Symbol(name) for name in symbols}


UNEVALUATED_SUM = Function("sum")
"""A sum written without an index or limits (``sum(x^n)``): an undefined function of its summand.

Two such sums are equal when their summands are; nothing is pulled out of
one (``2*sum(x)`` is not ``sum(2*x)``), since which symbol is the index is unknown.
"""


def _summation(*args: Any) -> Any:
    """An unevaluated ``Sum``, or :data:`UNEVALUATED_SUM` when called with just a summand.

    A sum with limits is never worked out while parsing, even with
    ``simplify``: ``sum(k!, (k, 1, 10**6))`` would not finish.
    """
    return UNEVALUATED_SUM(*args) if len(args) == 1 else Sum(*args)


def _base_symbol_dict(params: ExpressionParams) -> dict[str, Any]:
    """Names SymPy would otherwise read as special objects, unless enabled by the parameters."""
    special: dict[str, Any] = {"beta": beta, "gamma": gamma, "zeta": zeta, "Lambda": Lambda, "Chi": Chi}
    if not params.special_functions:
        special = {name: Symbol(name) for name in special}
    return {
        **special,
        "summation": _summation,
        "I": I if params.complex_numbers else Symbol("I"),
        "N": Symbol("N"),
        "O": Symbol("O"),
        "Q": Symbol("Q"),
        "S": Symbol("S"),
        "E": E if params.elementary_functions else Symbol("E"),
    }


# SympyParsingConfig fields that SympyParsingConfig.replace sets itself, not on its params.
_OWN_FIELDS = ("extra_unsplittable_symbols", "extra_symbol_assumptions")


@dataclass(frozen=True)
class SympyParsingConfig:
    """Everything :func:`parse_expression` needs: the task's parameters and what is derived from them.

    Build it with :meth:`from_params`; use :meth:`replace` for variants.
    """

    params: ExpressionParams
    extra_unsplittable_symbols: tuple[str, ...] = ()
    """Names never split, beyond the parameters' own (e.g. unit names), listed first."""
    extra_symbol_assumptions: tuple[tuple[str, str], ...] = ()
    """``(symbol, assumption)`` pairs applied before the parameters' own."""
    unsplittable_symbols: tuple[str, ...] = field(init=False, compare=False)
    """Names never split by implicit multiplication (``ab`` is not ``a*b`` if ``ab`` is listed)."""
    symbol_dict: Mapping[str, Any] = field(init=False, compare=False)
    """``local_dict`` for ``parse_expr``: names mapped to SymPy objects."""
    constants: frozenset[str] = field(init=False, compare=False)
    """Symbols declared constant via ``symbol_assumptions`` (their Symbols also carry ``constant=True``)."""

    def __post_init__(self) -> None:
        params = self.params
        unsplittable = [*self.extra_unsplittable_symbols, *params.reserved_keywords]
        unsplittable += [code for code in params.symbols if len(code) > 1]
        symbol_dict = {**_base_symbol_dict(params), **sympy_symbols(unsplittable)}
        constants: set[str] = set()
        for symbol, assumption in (*self.extra_symbol_assumptions, *params.symbol_assumptions):
            # Assumptions become Symbol keyword arguments; SymPy stores any identifier.
            if not assumption.isidentifier():
                raise SymbolAssumptionError(
                    f"Assumption {assumption} for symbol {symbol} is not a valid assumption name.",
                    symbol=symbol,
                    assumption=assumption,
                )
            if assumption.lower() == "constant":
                constants.add(symbol)  # also a Symbol assumption, below
            try:
                if assumption.lower() == "function":
                    symbol_dict[symbol] = Function(symbol)
                else:
                    symbol_dict[symbol] = Symbol(symbol, **{assumption: True})
            except Exception as e:
                raise SymbolAssumptionError(
                    f"Assumption {assumption} for symbol {symbol} caused a problem.",
                    symbol=symbol,
                    assumption=assumption,
                ) from e
        object.__setattr__(self, "unsplittable_symbols", tuple(unsplittable))
        object.__setattr__(self, "symbol_dict", symbol_dict)
        object.__setattr__(self, "constants", frozenset(constants))

    @classmethod
    def from_params(
        cls,
        params: ExpressionParams,
        unsplittable_symbols: Iterable[str] = (),
        symbol_assumptions: Iterable[tuple[str, str]] = (),
    ) -> SympyParsingConfig:
        """The configuration for ``params``; extra unsplittable symbols and assumptions come first."""
        return cls(params, tuple(unsplittable_symbols), tuple(symbol_assumptions))

    def replace(self, **changes: Any) -> SympyParsingConfig:
        """A copy with some parameters changed (``config.replace(strict_syntax=True)``).

        ``extra_unsplittable_symbols`` and ``extra_symbol_assumptions`` change the
        configuration's own fields; any other name changes its ``params``.
        """
        own = {name: changes.pop(name) for name in _OWN_FIELDS if name in changes}
        params = self.params.replace(**changes) if changes else self.params
        return replace(self, params=params, **own)

    @cached_property
    def substitution_params(self) -> ExpressionParams:
        """The (narrow) substitutions :func:`parse_expression` applies itself.

        Symbol aliases are *not* substituted here: callers run
        :func:`preprocess_expression` with the task's parameters first.
        """
        return ExpressionParams(
            reserved_keywords=self.params.reserved_keywords,
            unsplittable_symbols=self.unsplittable_symbols,
            elementary_functions=self.params.elementary_functions,
        )

    def transformations(self) -> tuple[Any, ...]:
        """``parse_expr`` transformations for this configuration.

        Not cached: ``split_symbols_custom`` returns a closure, which would stop the config pickling.
        """
        # _keywords_as_names goes after auto_symbol (which leaves keywords alone, and
        # would wrap our Symbol('in') again), before the symbol splitting.
        leading = (lambda_notation, auto_symbol, _keywords_as_names, repeated_decimals, auto_number)
        transformations: tuple[Any, ...]
        if self.params.strict_syntax:
            transformations = (*leading, function_exponentiation)
        else:
            unsplittable = set(self.unsplittable_symbols)

            def can_split(name: str) -> bool:
                return name not in unsplittable and _token_splittable(name)

            transformations = (
                *leading,
                factorial_notation,
                convert_xor,
                function_exponentiation,
                split_symbols_custom(can_split),
                implicit_multiplication,
                convert_equals_signs,
            )
        return (*transformations, rationalize) if self.params.rationalise else transformations


def _parse_expr(expr: str, **kwargs: Any) -> Any:
    """:func:`safe_parse_expr` that rejects arithmetic on non-expressions.

    With ``{}`` read as set literals (strict syntax), inputs like
    ``{x+1}*{x-1}`` build ``Mul(FiniteSet, FiniteSet)``, and an unrecognised
    function name before its arguments (``xmax(a, b)`` without
    ``elementary_functions``) multiplies by the ``Tuple`` ``(a, b)``. SymPy
    only deprecates such arithmetic (and will reject it in future). Other
    warnings pass through.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        parsed = safe_parse_expr(expr, **kwargs)
    for warning in caught:
        if issubclass(warning.category, SymPyDeprecationWarning) and "non-Expr" in str(warning.message):
            raise ExpressionParsingError(_non_expr_message(str(warning.message), expr), expression=expr)
        warnings.warn_explicit(warning.message, warning.category, warning.filename, warning.lineno)
    return parsed


def _warning_type_name(warning: str) -> str | None:
    """The ``name`` in the first ``has type 'name'`` of a warning, if any."""
    marker = "has type '"
    index = warning.find(marker)
    while index != -1:
        start = index + len(marker)
        name, quote, _ = warning[start:].partition("'")
        if quote and name and all(char.isalnum() or char == "_" for char in name):
            return name
        index = warning.find(marker, index + 1)
    return None


def _non_expr_message(warning: str, expr: str) -> str:
    """Explain SymPy's "non-Expr arguments" warning in terms of what the learner wrote."""
    kind = getattr(sympy, type_name, None) if (type_name := _warning_type_name(warning)) else None
    if isinstance(kind, type) and issubclass(kind, Set):
        return f"Arithmetic on a set ({{...}}) is not supported in {expr!r}; use ( ) for grouping."
    if kind is Tuple:
        return (
            f"A bracketed list such as (a, b) can't be used in arithmetic in {expr!r}. "
            "If it is meant as a function's arguments, check the function's name."
        )
    return f"{expr!r} combines something that isn't a number or expression (e.g. a comparison) in arithmetic."


def _unapplied_function(expr: str, symbol_dict: Mapping[str, Any]) -> str | None:
    """The first function name in ``expr`` not followed by its bracketed arguments (``sin x``), if any."""
    try:
        tokens = [token for token in generate_tokens(StringIO(expr).readline) if token.type in (NAME, OP)]
    except (TokenError, SyntaxError):
        return None
    values = [token.string for token in tokens]
    for index, token in enumerate(tokens):
        following = _following(values, index)
        if token.type != NAME or following in _APPLIED:
            continue
        if _reads_as_letters(token.string, following, symbol_dict):
            continue  # read as letters (see _keywords_as_names)
        obj = symbol_dict[token.string] if token.string in symbol_dict else MATH_NAMESPACE.get(token.string)
        if callable(obj) and not isinstance(obj, Basic):
            return token.string
    return None


def _parse_one(expr: str, config: SympyParsingConfig, transformations: tuple[Any, ...]) -> Basic:
    if not config.params.strict_syntax:
        expr = convert_bracket_notation(expr)
    try:
        expr = _substitute_names(apply_convention(expr, config.params.convention), config)
        logger.debug("parse: convention %s and names applied: %r", config.params.convention, expr)
        parsed = _evaluate(expr, config, transformations)
        logger.debug("parse %r -> %s", expr, parsed)
        return parsed
    except RecursionError as e:
        raise ExpressionParsingError(TOO_DEEP_MESSAGE, expression=expr) from e
    except Exception as e:
        function = _unapplied_function(expr, config.symbol_dict)
        if function is not None:
            raise ExpressionParsingError(
                f"{function} is a function, so its argument needs brackets: {function}(...)", expression=expr
            ) from e
        if isinstance(e, ExpressionParsingError):
            raise
        # Tokenizer, convention-parser and evaluation failures all mean "not a valid expression".
        raise ExpressionParsingError(f"Failed to parse expression {expr!r}: {e}", expression=expr) from e


def _substitute_names(expr: str, config: SympyParsingConfig) -> str:
    """Pad unsplittable symbols and function names, and spell out Greek letters."""
    substitutions: list[Substitution] = [(name, f" {name} ") for name in config.unsplittable_symbols]
    substitutions += greek_symbol_substitutions(expr)
    if config.params.elementary_functions:
        substitutions += elementary_function_substitutions(expr)
    return " ".join(substitute(expr, sorted_substitutions(substitutions)).split())


def _evaluate(expr: str, config: SympyParsingConfig, transformations: tuple[Any, ...]) -> Basic:
    symbol_dict = dict(config.symbol_dict)
    sides = split_equation(expr, ExpressionParsingError)
    parsed: Any
    if len(sides) == 2:
        # Each side as if it were a whole expression: unevaluated unless simplifying
        # (evaluating 9**9**9 = x would never finish).
        lhs, rhs = (_parse_side(side, config, transformations, symbol_dict) for side in sides)
        parsed = Equality(lhs, rhs, evaluate=False)
    else:
        parsed = _parse_side(expr, config, transformations, symbol_dict)
    if not isinstance(parsed, Basic):
        raise ExpressionParsingError(f"Failed to parse Sympy expression `{expr}`", expression=expr)
    return parsed


def _parse_side(
    expr: str, config: SympyParsingConfig, transformations: tuple[Any, ...], symbol_dict: dict[str, Any]
) -> Any:
    """An expression (or one side of an equation): simplified, or else left unevaluated."""
    unevaluated = _parse_expr(expr, transformations=transformations, local_dict=symbol_dict, evaluate=False)
    if not config.params.simplify:
        return unevaluated
    if isinstance(unevaluated, Basic):
        check_evaluation_cost(unevaluated, expr)
    parsed = _parse_expr(expr, transformations=transformations, local_dict=symbol_dict)
    return parsed.simplify() if isinstance(parsed, Basic) else parsed


def parse_expressions(expr: str, config: SympyParsingConfig) -> tuple[Basic, ...]:
    """Parse a (preprocessed) response into the SymPy expressions it stands for.

    Usually one, but ``{a, b}`` and ``±`` stand for several. They come in the
    order written, each once. ``a = b`` gives an unevaluated ``Equality``.
    Raises :class:`ExpressionParsingError` for text longer than :data:`MAX_INPUT_LENGTH`.
    """
    check_input_length(expr)
    transformations = config.transformations()
    parsed = (
        _parse_one(text, config, transformations) for text in create_expression_set(expr, config.substitution_params)
    )
    return tuple(dict.fromkeys(parsed))


def parse_expression(expr: str, config: SympyParsingConfig) -> Basic:
    """Parse a (preprocessed) response that stands for one expression (see :func:`parse_expressions`).

    Raises :class:`ExpressionParsingError` if it stands for several (``{a, b}`` or ``±``).
    """
    expressions = parse_expressions(expr, config)
    if len(expressions) > 1:
        raise ExpressionParsingError(
            f"{expr!r} stands for {len(expressions)} expressions, not one; use parse_expressions.", expression=expr
        )
    return expressions[0]
