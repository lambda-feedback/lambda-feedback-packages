"""LaTeX output (SymPy → LaTeX) and input (LaTeX → SymPy string)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from latex2sympy2 import latex2sympy
from sympy import Function, Symbol
from sympy.core.function import AppliedUndef
from sympy.parsing.sympy_parser import implicit_multiplication_application, standard_transformations
from sympy.printing.latex import LatexPrinter

from ._safe_parse import safe_parse_expr
from .errors import LatexParseError
from .params import SymbolSpec
from .preprocessing import _expand_plus_minus, find_matching_parenthesis

# Symbol aliases are parsed with ``Symbol`` as the only name: an alias that
# needs anything more (a number, a function call) falls back to a plain name.
_ALIAS_NAMESPACE = {"Symbol": Symbol}

# \pm and \mp as commands (so not the start of e.g. \pmod), with any space after.
_PM_RE = re.compile(r"\\pm(?![A-Za-z])\s*")
_MP_RE = re.compile(r"\\mp(?![A-Za-z])\s*")

SYMBOL_LATEX_RE = re.compile(r"(?P<start>\\\(|\$\$|\$)(?P<latex>.*?)(?P<end>\\\)|\$\$|\$)")
"""Finds math-mode LaTeX (``\\(...\\)``, ``$$...$$`` or ``$...$``) in a symbol's LaTeX string."""


class _LatexPrinter(LatexPrinter):
    """SymPy's LaTeX printer, but printing logarithms with a base as ``\\log_{b}``."""

    def _print_log(self, expr: Any, exp: Any = None) -> str:
        log_not = r"\ln" if self._settings["ln_notation"] and len(expr.args) < 2 else r"\log"
        if len(expr.args) > 1:
            base = self._print(expr.args[1])
            log_not = rf"\log_{{{base}}}"
        tex = rf"{log_not}{{\left({self._print(expr.args[0])} \right)}}"
        return rf"{tex}^{{{exp}}}" if exp is not None else tex


def extract_latex(symbol: str) -> str:
    """The math-mode part of a symbol's LaTeX string (the first one), or the whole string."""
    match = SYMBOL_LATEX_RE.search(symbol)
    return symbol if match is None else match.group("latex")


def latex_symbols(symbols: Mapping[str, SymbolSpec]) -> dict[Symbol, str]:
    """``{Symbol(code): latex}`` for the LaTeX printer; symbols without LaTeX are left out."""
    return {Symbol(code): extract_latex(spec.latex) for code, spec in symbols.items() if spec.latex is not None}


def sympy_to_latex(
    expression: Any, symbols: Mapping[str, SymbolSpec], settings: Mapping[str, Any] | None = None
) -> str:
    """LaTeX for a SymPy expression, printing task symbols with their LaTeX.

    ``settings`` are ``sympy.latex`` settings; ``ln_notation`` defaults to True.
    """
    names = latex_symbols(symbols)
    # The printer looks symbols up by equality, and a symbol with assumptions
    # (Symbol('x', positive=True), from symbol_assumptions) != Symbol('x').
    by_name = {symbol.name: latex for symbol, latex in names.items()}
    for symbol in getattr(expression, "free_symbols", ()):
        if isinstance(symbol, Symbol) and symbol.name in by_name:
            names[symbol] = by_name[symbol.name]
    settings = {"symbol_names": names, "ln_notation": True, **(settings or {})}
    return str(_LatexPrinter(settings).doprint(expression))


# ----------------------------------------------------------------------
# LaTeX input
# ----------------------------------------------------------------------


def find_placeholder(exp: str) -> str | None:
    """A letter not occurring in ``exp`` (``None`` if every candidate does)."""
    for char in "abcdfghjkoqrtvwxyzABCDFGHIJKLMNOPQRSTUVWXYZ":
        if char not in exp:
            return char
    return None


# A LaTeX command (left alone), scientific notation (2E5, 1.5e-3: the E is
# kept, as an upper-case E, which latex2sympy reads as an exponent), or any
# other E or e.
_E_OR_COMMAND = re.compile(r"(\\[A-Za-z]+)|(?<=[\d.])([Ee])(?=[+-]?\d)|([Ee])")


def preprocess_E(latex_str: str) -> tuple[str, dict[str, str]]:  # noqa: N802
    """Replace each ``E``/``e`` (outside commands and scientific notation) by a placeholder letter.

    latex2sympy reads them inconsistently: ``e`` as Euler's number
    (``e_1 e_2`` gives ``E``), and ``E`` after a digit as an exponent (``2E``
    gives ``2``). As placeholders they are plain symbols, restored by
    :func:`postprocess_E`, so whether ``e`` is Euler's number is left to
    :func:`parse_expression` (``elementary_functions``), as for text input.
    Returns the modified string and ``{"E" or "e": placeholder}``.
    """
    replacements: dict[str, str] = {}
    for char in "Ee":
        if any(match.group(3) == char for match in _E_OR_COMMAND.finditer(latex_str)):
            placeholder = find_placeholder(latex_str + "".join(replacements.values()))
            if placeholder:
                replacements[char] = placeholder

    def repl(match: re.Match[str]) -> str:
        command, exponent, letter = match.groups()
        if command:
            return command
        if exponent:
            return "E"
        return replacements.get(letter, letter)

    return _E_OR_COMMAND.sub(repl, latex_str), replacements


def postprocess_E(expr: Any, replacements: Mapping[str, str]) -> Any:  # noqa: N802
    """Undo :func:`preprocess_E` on the symbols (and undefined functions) of a parsed expression."""
    if not replacements:
        return expr
    restore = str.maketrans({placeholder: char for char, placeholder in replacements.items()})
    subs: dict[Any, Any] = {}
    for symbol in expr.atoms(Symbol):
        name = symbol.name.translate(restore)
        if name != symbol.name:
            subs[symbol] = Symbol(name, **symbol.assumptions0)
    for application in expr.atoms(AppliedUndef):
        name = application.func.__name__.translate(restore)
        if name != application.func.__name__:
            subs[application] = Function(name)(*application.args)
    return expr.xreplace(subs)


def _latex2sympy(latex: str, substitutions: Mapping[Any, Any] | None = None) -> Any:
    """latex2sympy with ``E``/``e`` read as plain symbols (see :func:`preprocess_E`)."""
    protected, replacements = preprocess_E(latex)
    parsed = latex2sympy(protected, substitutions) if substitutions is not None else latex2sympy(protected)
    if isinstance(parsed, list):
        parsed = parsed.pop()
    return postprocess_E(parsed, replacements)


def parse_latex(response: str, symbols: Mapping[str, SymbolSpec], simplify: bool = False) -> str:
    """Parse LaTeX into a SymPy-syntax string, mapping task symbols to their codes.

    With ``simplify`` the expression is simplified first; otherwise it stays
    as close to the input as possible. ``\\pm``/``\\mp`` give both signs, as
    ``{a, b}``, and an equation gives ``lhs = rhs`` (each side simplified
    separately with ``simplify``). The result is text for
    :func:`parse_expression`. Raises :class:`LatexParseError` if the
    response or a symbol's LaTeX can't be parsed.
    """
    substitutions: dict[Any, Any] = {}

    expanded = _MP_RE.sub("minus_plus", _PM_RE.sub("plus_minus", response))
    responses = list(dict.fromkeys(_expand_plus_minus(expanded)))

    alias_transformations = (*standard_transformations, implicit_multiplication_application)
    for code, spec in symbols.items():
        if spec.latex is None or r"\pm" in spec.latex or r"\mp" in spec.latex:
            continue
        latex = extract_latex(spec.latex)
        try:
            substitutions[_latex2sympy(latex)] = Symbol(code)
        except Exception as e:
            raise LatexParseError(f"Couldn't parse latex symbol {latex} to sympy symbol.", symbol=latex) from e
        for alias in spec.aliases:
            try:
                parsed_alias = safe_parse_expr(
                    alias,
                    transformations=alias_transformations,
                    global_dict=_ALIAS_NAMESPACE,
                    local_dict={"E": Symbol("E")},
                )
            except Exception:
                parsed_alias = Symbol(alias)  # not an expression: use the alias as a plain name
            substitutions[parsed_alias] = Symbol(code)

    def side_text(latex: str) -> str:
        parsed = _latex2sympy(latex, substitutions)
        return str((parsed.simplify() if simplify else parsed).subs(substitutions))

    parsed_responses = set()
    for expression in responses:
        if expression.count("=") > 1:
            raise LatexParseError(f"An expression can contain at most one '=': {expression}", expression=expression)
        try:
            # An equation is written "lhs = rhs", as parse_expression reads it. (PyPI's
            # latex2sympy2 reads "x = 2" as an assignment, so the sides are parsed
            # separately; and "Eq(x, 2)" would not survive parse_expression with
            # elementary_functions, where the E of Eq is Euler's number.)
            parsed_responses.add(" = ".join(side_text(side) for side in expression.split("=")))
        except Exception as e:
            raise LatexParseError(f"Failed to parse expression {expression!r}: {e}", expression=expression) from e

    if len(parsed_responses) < 2:
        return parsed_responses.pop()
    return "{" + ", ".join(sorted(parsed_responses)) + "}"


def sanitise_latex(response: str) -> str:
    """Remove whitespace, turn ``~`` into spaces and unwrap ``\\mathrm{...}`` / ``\\text{...}``."""
    response = "".join(response.split()).replace("~", " ")
    for wrapper in (r"\mathrm", r"\text"):
        processed = []
        index = 0
        while index < len(response):
            wrapper_start = response.find(wrapper + "{", index)
            if wrapper_start < 0:
                processed.append(response[index:])
                break
            processed.append(response[index:wrapper_start])
            wrapper_end = find_matching_parenthesis(response, wrapper_start + 1, delimiters=("{", "}"))
            if wrapper_end < 0:
                raise LatexParseError(f"Unclosed {wrapper}{{...}} in {response!r}.", response=response, wrapper=wrapper)
            processed.append(response[wrapper_start + len(wrapper) + 1 : wrapper_end])
            index = wrapper_end + 1
        response = "".join(processed)
    return response
