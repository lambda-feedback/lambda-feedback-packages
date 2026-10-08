"""Typed parameters for expression parsing.

Evaluation functions receive their parameters as a JSON object. Use
:meth:`ExpressionParams.from_dict` to turn it into an :class:`ExpressionParams`;
unrelated keys are ignored.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, fields, replace
from types import MappingProxyType
from typing import Any, Literal, Self, get_args

from .errors import InvalidParameterError, SymbolAssumptionError, UnknownConventionError
from .preprocessing import find_matching_parenthesis

Convention = Literal["equal_precedence", "implicit_higher_precedence"]
"""How implicit multiplication binds relative to ``/``: ``a/bc`` is ``a/b*c`` or ``a/(b*c)``."""


def validate_convention(convention: Convention | None) -> None:
    """Raise :class:`UnknownConventionError` unless ``convention`` is ``None`` or recognised."""
    if convention is not None and convention not in get_args(Convention):
        raise UnknownConventionError(convention)


@dataclass(frozen=True)
class SymbolSpec:
    """A task-defined symbol: its LaTeX and the other ways a learner may write it."""

    latex: str | None = None
    aliases: tuple[str, ...] = ()


def _strings(name: str, value: Any) -> tuple[str, ...]:
    """``value`` as a tuple of strings; a bare string is rejected rather than split into characters."""
    if isinstance(value, str) or not isinstance(value, Iterable):
        raise InvalidParameterError(name, f"expected a list of strings, got {value!r}")
    items = tuple(value)
    if not all(isinstance(item, str) for item in items):
        raise InvalidParameterError(name, f"expected a list of strings, got {value!r}")
    return items


def _normalise_symbols(symbols: Mapping[str, SymbolSpec | Mapping[str, Any]]) -> Mapping[str, SymbolSpec]:
    """Drop blank codes, strip aliases and drop blank ones, and move ``lambda`` to ``lamda``.

    ``lambda`` is a Python keyword, so it is parsed as the symbol ``lamda``
    (which always exists, with ``lambda`` as an alias).
    """
    if not isinstance(symbols, Mapping):
        raise InvalidParameterError("symbols", f"expected a mapping of symbol codes, got {symbols!r}")
    normalised: dict[str, SymbolSpec] = {}
    for code, spec in symbols.items():
        if not isinstance(code, str):
            raise InvalidParameterError("symbols", f"symbol codes must be strings, got {code!r}")
        if not code.strip():
            continue
        if isinstance(spec, Mapping):
            spec = SymbolSpec(latex=spec.get("latex"), aliases=spec.get("aliases", ()))
        elif not isinstance(spec, SymbolSpec):
            raise InvalidParameterError("symbols", f"symbol {code!r} must be a mapping, got {spec!r}")
        if spec.latex is not None and not isinstance(spec.latex, str):
            raise InvalidParameterError("symbols", f"the latex of symbol {code!r} must be a string")
        aliases = tuple(alias.strip() for alias in _strings("symbols", spec.aliases) if alias.strip())
        normalised[code] = SymbolSpec(spec.latex, aliases)
    if "lambda" in normalised and "lamda" in normalised:
        raise InvalidParameterError("symbols", "'lambda' and 'lamda' are the same symbol; define only one")
    lamda = normalised.pop("lambda", None) or normalised.get("lamda") or SymbolSpec(r"\lambda")
    if "lambda" not in lamda.aliases:
        lamda = SymbolSpec(lamda.latex, (*lamda.aliases, "lambda"))
    normalised["lamda"] = lamda
    return MappingProxyType(normalised)


def _normalise_input_symbols(entries: Iterable[Any]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Legacy ``[[code, [alternatives]], ...]``: drop blank codes, strip and drop blank alternatives."""
    if isinstance(entries, str) or not isinstance(entries, Iterable):
        raise InvalidParameterError("input_symbols", f"expected a list of [code, [alternatives]], got {entries!r}")
    normalised = []
    for entry in entries:
        if isinstance(entry, str) or not isinstance(entry, Sequence) or (entry and not isinstance(entry[0], str)):
            raise InvalidParameterError("input_symbols", f"expected [code, [alternatives]], got {entry!r}")
        code = entry[0].strip() if entry else ""
        if code:
            alternatives = _strings("input_symbols", entry[1]) if len(entry) > 1 else ()
            normalised.append((code, tuple(a.strip() for a in alternatives if a.strip())))
    return tuple(normalised)


def parse_symbol_assumptions(text: str) -> tuple[tuple[str, str], ...]:
    """Parse ``"('a','positive') ('f','function')"`` into ``(('a', 'positive'), ('f', 'function'))``.

    Each parenthesised group must be a pair of string literals; nothing is
    evaluated as code.
    """
    assumptions = []
    index = text.find("(")
    while index > -1:
        index_match = find_matching_parenthesis(text, index)
        if index_match < 0:
            raise SymbolAssumptionError("List of symbol assumptions not written correctly.", text=text)
        try:
            value = ast.literal_eval(text[index + 1 : index_match])
        except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError) as e:
            raise SymbolAssumptionError("List of symbol assumptions not written correctly.", text=text) from e
        if not (isinstance(value, tuple) and len(value) == 2 and all(isinstance(v, str) for v in value)):
            pair_text = text[index : index_match + 1]
            raise SymbolAssumptionError(
                f"Symbol assumption {pair_text} must be a pair of strings, e.g. ('x', 'positive').",
                text=pair_text,
            )
        assumptions.append(value)
        index = text.find("(", index_match + 1)
    return tuple(assumptions)


# JSON parameter names that differ from the field names.
_ALIASES = {"complexNumbers": "complex_numbers", "specialFunctions": "special_functions"}


@dataclass(frozen=True)
class ExpressionParams:
    """Parameters controlling how expressions are preprocessed and parsed.

    ``symbols`` is normalised on construction (see :func:`_normalise_symbols`),
    so every instance has a ``lamda`` symbol.
    """

    complex_numbers: bool = False
    """Treat ``I`` as the imaginary unit (otherwise it is a plain symbol)."""
    convention: Convention | None = "equal_precedence"
    """Implicit-multiplication precedence, or ``None`` to leave the input as written."""
    elementary_functions: bool = False
    """Recognise function names and aliases (``sin``, ``arcsin``, ``ln``, ...), Greek letters and ``E``."""
    special_functions: bool = False
    """Parse ``beta``, ``gamma``, ``zeta``, ``Lambda`` and ``Chi`` as SymPy's special functions."""
    strict_syntax: bool = False
    """Require explicit syntax: no implicit multiplication, ``[]``/``{}`` are not brackets."""
    simplify: bool = False
    rationalise: bool = True
    """Parse decimals as rationals."""
    is_latex: bool = False
    """The response is LaTeX: for callers to choose :func:`parse_latex` (this package doesn't read it)."""
    symbols: Mapping[str, SymbolSpec] = field(default_factory=dict)
    input_symbols: tuple[tuple[str, tuple[str, ...]], ...] = ()
    """Legacy ``[code, [alternatives]]`` symbol definitions."""
    reserved_keywords: tuple[str, ...] = ()
    unsplittable_symbols: tuple[str, ...] = ()
    symbol_assumptions: tuple[tuple[str, str], ...] = ()
    """``(symbol, assumption)`` pairs, e.g. ``("x", "positive")``, ``("f", "function")``."""
    plus_minus: str | None = None
    """Text the learner uses for ±, replaced by ``plus_minus``."""
    minus_plus: str | None = None

    def __post_init__(self) -> None:
        # Parameters usually come from JSON (via from_dict), so check the types.
        for name in _BOOL_FIELDS:
            if not isinstance(getattr(self, name), bool):
                raise InvalidParameterError(name, f"expected true or false, got {getattr(self, name)!r}")
        for name in ("plus_minus", "minus_plus"):
            if getattr(self, name) is not None and not isinstance(getattr(self, name), str):
                raise InvalidParameterError(name, f"expected a string, got {getattr(self, name)!r}")
        validate_convention(self.convention)
        object.__setattr__(self, "symbols", _normalise_symbols(self.symbols))
        object.__setattr__(self, "input_symbols", _normalise_input_symbols(self.input_symbols))
        object.__setattr__(self, "reserved_keywords", _strings("reserved_keywords", self.reserved_keywords))
        object.__setattr__(self, "unsplittable_symbols", _strings("unsplittable_symbols", self.unsplittable_symbols))
        pairs = tuple(_strings("symbol_assumptions", pair) for pair in self.symbol_assumptions)
        if any(len(pair) != 2 for pair in pairs):
            raise InvalidParameterError("symbol_assumptions", "expected (symbol, assumption) pairs")
        object.__setattr__(self, "symbol_assumptions", pairs)

    @classmethod
    def from_dict(cls, params: Mapping[str, Any]) -> Self:
        """Build from evaluation-function parameters (JSON keys); unrelated keys are ignored."""
        names = {f.name for f in fields(cls)}
        values = {_ALIASES.get(key, key): value for key, value in params.items()}
        values = {key: value for key, value in values.items() if key in names}
        if isinstance(values.get("symbol_assumptions"), str):
            values["symbol_assumptions"] = parse_symbol_assumptions(values["symbol_assumptions"])
        return cls(**values)

    def replace(self, **changes: Any) -> Self:
        """A copy with some fields changed."""
        return replace(self, **changes)


_BOOL_FIELDS = tuple(f.name for f in fields(ExpressionParams) if f.type == "bool")
