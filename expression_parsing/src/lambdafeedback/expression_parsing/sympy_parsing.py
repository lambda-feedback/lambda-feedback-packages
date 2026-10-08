"""Parsing preprocessed expressions into SymPy objects."""

from __future__ import annotations

import warnings
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import cached_property
from typing import Any

from sympy import Basic, Equality, Function, Symbol
from sympy.parsing.sympy_parser import T as TRANSFORMATIONS
from sympy.parsing.sympy_parser import _token_splittable, split_symbols_custom
from sympy.utilities.exceptions import SymPyDeprecationWarning

from ._safe_parse import safe_parse_expr
from .conventions import apply_convention
from .errors import ExpressionParsingError, SymbolAssumptionError
from .params import Convention, ExpressionParams
from .preprocessing import convert_bracket_notation, create_expression_set
from .substitution import _sorted, elementary_function_substitutions, greek_symbol_substitutions, substitute


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
        return tuple(transformations)


def _parse_expr(expr: str, **kwargs: Any) -> Any:
    """:func:`safe_parse_expr` that rejects arithmetic on non-expressions.

    With ``{}`` read as set literals (strict syntax), inputs like
    ``{x+1}*{x-1}`` build ``Mul(FiniteSet, FiniteSet)``, which SymPy only
    deprecates (and will reject in future). Other warnings pass through.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        parsed = safe_parse_expr(expr, **kwargs)
    for warning in caught:
        if issubclass(warning.category, SymPyDeprecationWarning) and "non-Expr" in str(warning.message):
            raise ExpressionParsingError(
                f"Arithmetic on a set ({{...}}) is not supported in {expr!r}; use ( ) for grouping.",
                expression=expr,
            )
        warnings.warn_explicit(warning.message, warning.category, warning.filename, warning.lineno)
    return parsed


def _parse_one(expr: str, config: SympyParsingConfig, transformations: tuple[Any, ...]) -> Basic:
    try:
        return _parse_one_unchecked(expr, config, transformations)
    except ExpressionParsingError:
        raise
    except Exception as e:
        # Tokenizer, convention-parser and evaluation failures all mean "not a valid expression".
        raise ExpressionParsingError(f"Failed to parse expression {expr!r}: {e}", expression=expr) from e


def _parse_one_unchecked(expr: str, config: SympyParsingConfig, transformations: tuple[Any, ...]) -> Basic:
    if not config.strict_syntax:
        expr = convert_bracket_notation(expr)
    expr = apply_convention(expr, config.convention)

    substitutions = [(name, f" {name} ") for name in config.unsplittable_symbols]
    substitutions += greek_symbol_substitutions(expr)
    if config.elementary_functions:
        substitutions += elementary_function_substitutions(expr)
    expr = " ".join(substitute(expr, _sorted(substitutions)).split())

    symbol_dict = dict(config.symbol_dict)
    if expr.count("=") > 1:
        raise ExpressionParsingError(f"An expression can contain at most one '=': {expr}", expression=expr)
    parsed: Any
    if "=" in expr:
        lhs, rhs = expr.split("=")
        parsed = Equality(
            _parse_expr(lhs, transformations=transformations, local_dict=symbol_dict),
            _parse_expr(rhs, transformations=transformations, local_dict=symbol_dict),
            evaluate=False,
        )
    elif config.simplify:
        parsed = _parse_expr(expr, transformations=transformations, local_dict=symbol_dict)
        if not isinstance(parsed, Equality):
            parsed = parsed.simplify()
    else:
        parsed = _parse_expr(expr, transformations=transformations, local_dict=symbol_dict, evaluate=False)
    if not isinstance(parsed, Basic):
        raise ExpressionParsingError(f"Failed to parse Sympy expression `{expr}`", expression=expr)
    return parsed


def parse_expression(expr_string: str | Sequence[str], config: SympyParsingConfig) -> Basic | set[Basic]:
    """Parse a (preprocessed) response into a SymPy expression.

    A response standing for several expressions (``{a, b}`` or ``±``) gives a
    set of them. ``a = b`` gives an unevaluated ``Equality``.
    """
    expressions = create_expression_set(expr_string, config.substitution_params)
    transformations = config.transformations()
    parsed = {_parse_one(expr, config, transformations) for expr in expressions}
    return parsed.pop() if len(expressions) == 1 else parsed
