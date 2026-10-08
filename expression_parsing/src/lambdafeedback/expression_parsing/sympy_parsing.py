"""Parsing preprocessed expressions into SymPy objects."""

from __future__ import annotations

import re
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
from sympy import Basic, Equality, Function, Set, Symbol, Tuple
from sympy.parsing.sympy_parser import T as TRANSFORMATIONS
from sympy.parsing.sympy_parser import _token_splittable, split_symbols_custom
from sympy.utilities.exceptions import SymPyDeprecationWarning

from ._safe_parse import MATH_NAMESPACE, safe_parse_expr
from .conventions import apply_convention
from .errors import ExpressionParsingError, SymbolAssumptionError
from .params import Convention, ExpressionParams
from .preprocessing import convert_bracket_notation, create_expression_set
from .substitution import (
    Substitution,
    _sorted,
    elementary_function_substitutions,
    greek_symbol_substitutions,
    substitute,
)
from .symbol_tables import EMBEDDABLE_FUNCTION_NAMES

_APPLIED = ("(", "**", "^")


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
    for index, (kind, value) in enumerate(tokens):
        following = tokens[index + 1][1] if index + 1 < len(tokens) else ""
        unapplied_function = value.casefold() in EMBEDDABLE_FUNCTION_NAMES and following not in _APPLIED
        if kind != NAME or not (iskeyword(value) or (unapplied_function and value not in local_dict)):
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


def _base_symbol_dict(params: ExpressionParams) -> dict[str, Any]:
    """Names SymPy would otherwise read as special objects, unless enabled by the parameters."""
    from sympy import Chi, E, I, Lambda, beta, gamma, zeta

    special: dict[str, Any] = {"beta": beta, "gamma": gamma, "zeta": zeta, "Lambda": Lambda, "Chi": Chi}
    if not params.special_functions:
        special = {name: Symbol(name) for name in special}
    return {
        **special,
        "I": I if params.complex_numbers else Symbol("I"),
        "N": Symbol("N"),
        "O": Symbol("O"),
        "Q": Symbol("Q"),
        "S": Symbol("S"),
        "E": E if params.elementary_functions else Symbol("E"),
    }


@dataclass(frozen=True)
class SympyParsingConfig:
    """Everything :func:`parse_expression` needs, derived from :class:`ExpressionParams`.

    Build it with :meth:`from_params`; use :meth:`replace` for variants.
    """

    unsplittable_symbols: tuple[str, ...] = ()
    """Names never split by implicit multiplication (``ab`` is not ``a*b`` if ``ab`` is listed)."""
    strict_syntax: bool = False
    symbol_dict: Mapping[str, Any] = field(default_factory=dict)
    """``local_dict`` for ``parse_expr``: names mapped to SymPy objects."""
    extra_transformations: tuple[Any, ...] = ()
    elementary_functions: bool = False
    convention: Convention | None = "equal_precedence"
    simplify: bool = False
    rationalise: bool = True
    constants: frozenset[str] = frozenset()
    """Symbols declared constant via ``symbol_assumptions``."""
    complex_numbers: bool = False
    reserved_keywords: tuple[str, ...] = ()

    @classmethod
    def from_params(
        cls,
        params: ExpressionParams,
        unsplittable_symbols: Iterable[str] = (),
        symbol_assumptions: Iterable[tuple[str, str]] = (),
    ) -> SympyParsingConfig:
        """Derive the configuration; extra unsplittable symbols and assumptions come first."""
        unsplittable = [*unsplittable_symbols, *params.reserved_keywords]
        unsplittable += [code for code in params.symbols if len(code) > 1]
        symbol_dict = {**_base_symbol_dict(params), **sympy_symbols(unsplittable)}
        constants: set[str] = set()
        for symbol, assumption in (*symbol_assumptions, *params.symbol_assumptions):
            # Assumptions become Symbol keyword arguments; SymPy stores any identifier.
            if not assumption.isidentifier():
                raise SymbolAssumptionError(
                    f"Assumption {assumption} for symbol {symbol} is not a valid assumption name.",
                    symbol=symbol,
                    assumption=assumption,
                )
            try:
                if assumption.lower() == "constant":
                    constants.add(symbol)
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
        return cls(
            unsplittable_symbols=tuple(unsplittable),
            strict_syntax=params.strict_syntax,
            symbol_dict=symbol_dict,
            elementary_functions=params.elementary_functions,
            convention=params.convention,
            simplify=params.simplify,
            rationalise=params.rationalise,
            constants=frozenset(constants),
            complex_numbers=params.complex_numbers,
            reserved_keywords=params.reserved_keywords,
        )

    def replace(self, **changes: Any) -> SympyParsingConfig:
        """A copy with some fields changed."""
        return replace(self, **changes)

    @cached_property
    def substitution_params(self) -> ExpressionParams:
        """The (narrow) substitutions :func:`parse_expression` applies itself.

        Symbol aliases are *not* substituted here: callers run
        :func:`preprocess_expression` with the task's parameters first.
        """
        return ExpressionParams(
            reserved_keywords=self.reserved_keywords,
            unsplittable_symbols=self.unsplittable_symbols,
            elementary_functions=self.elementary_functions,
        )

    def transformations(self) -> tuple[Any, ...]:
        if self.strict_syntax:
            transformations = TRANSFORMATIONS[0:4, 10] + self.extra_transformations
        else:
            unsplittable = set(self.unsplittable_symbols)

            def can_split(name: str) -> bool:
                return name not in unsplittable and _token_splittable(name)

            transformations = (
                TRANSFORMATIONS[0:5, 6, 10]
                + self.extra_transformations
                + (split_symbols_custom(can_split),)
                + TRANSFORMATIONS[8, 9]
            )
        if self.rationalise:
            transformations += TRANSFORMATIONS[11]
        # After auto_symbol (which leaves keywords alone, and would wrap our
        # Symbol('in') again), before the symbol splitting.
        lambda_notation, auto_symbol, *rest = transformations
        return (lambda_notation, auto_symbol, _keywords_as_names, *rest)


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


def _non_expr_message(warning: str, expr: str) -> str:
    """Explain SymPy's "non-Expr arguments" warning in terms of what the learner wrote."""
    match = re.search(r"has type '(\w+)'", warning)
    kind = getattr(sympy, match.group(1), None) if match else None
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
    for index, token in enumerate(tokens):
        following = tokens[index + 1].string if index + 1 < len(tokens) else ""
        if token.type != NAME or following in _APPLIED:
            continue
        if token.string not in symbol_dict and token.string.casefold() in EMBEDDABLE_FUNCTION_NAMES:
            continue  # read as letters (see _keywords_as_names)
        obj = symbol_dict[token.string] if token.string in symbol_dict else MATH_NAMESPACE.get(token.string)
        if callable(obj) and not isinstance(obj, Basic):
            return token.string
    return None


def _parse_one(expr: str, config: SympyParsingConfig, transformations: tuple[Any, ...]) -> Basic:
    if not config.strict_syntax:
        expr = convert_bracket_notation(expr)
    try:
        expr = _substitute_names(apply_convention(expr, config.convention), config)
        return _evaluate(expr, config, transformations)
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
    if config.elementary_functions:
        substitutions += elementary_function_substitutions(expr)
    return " ".join(substitute(expr, _sorted(substitutions)).split())


def _evaluate(expr: str, config: SympyParsingConfig, transformations: tuple[Any, ...]) -> Basic:
    symbol_dict = dict(config.symbol_dict)
    if expr.count("=") > 1:
        raise ExpressionParsingError(f"An expression can contain at most one '=': {expr}", expression=expr)
    parsed: Any
    if "=" in expr:
        # Each side as if it were a whole expression: unevaluated unless simplifying
        # (evaluating 9**9**9 = x would never finish).
        lhs, rhs = (_parse_side(side, config, transformations, symbol_dict) for side in expr.split("="))
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
    if not config.simplify:
        return _parse_expr(expr, transformations=transformations, local_dict=symbol_dict, evaluate=False)
    parsed = _parse_expr(expr, transformations=transformations, local_dict=symbol_dict)
    return parsed.simplify() if isinstance(parsed, Basic) else parsed


def parse_expression(expr_string: str | Sequence[str], config: SympyParsingConfig) -> Basic | set[Basic]:
    """Parse a (preprocessed) response into a SymPy expression.

    A response standing for several expressions (``{a, b}`` or ``±``) gives a
    set of them. ``a = b`` gives an unevaluated ``Equality``.
    """
    expressions = create_expression_set(expr_string, config.substitution_params)
    transformations = config.transformations()
    parsed = {_parse_one(expr, config, transformations) for expr in expressions}
    return parsed.pop() if len(expressions) == 1 else parsed
