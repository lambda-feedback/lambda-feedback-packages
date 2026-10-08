"""LaTeX output (SymPy → LaTeX) and input (LaTeX → SymPy string)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from latex2sympy2 import latex2sympy
from sympy import Eq, Symbol
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
    settings = {"symbol_names": latex_symbols(symbols), "ln_notation": True, **(settings or {})}
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


def preprocess_E(latex_str: str) -> tuple[str, dict[str, str]]:  # noqa: N802
    """Replace names starting with ``E``/``e`` by placeholders so latex2sympy doesn't read Euler's number.

    Returns the modified string and ``{"E" or "e": placeholder}``.
    """
    replacements: dict[str, str] = {}
    if re.search(r"(?<!\\)E(?:[a-zA-Z_][a-zA-Z0-9_]*|_\{[^}]*\})?", latex_str):
        placeholder = find_placeholder(latex_str)
        if placeholder:
            replacements["E"] = placeholder
    if re.search(r"(?<!\\)e(?:[a-zA-Z_][a-zA-Z0-9_]*|_\{[^}]*\})?", latex_str):
        placeholder = find_placeholder(latex_str + "".join(replacements.values()))
        if placeholder:
            replacements["e"] = placeholder
    if not replacements:
        return latex_str, {}

    def repl(match: re.Match[str]) -> str:
        token = match.group(0)
        return replacements[token[0]] + token[1:] if token[0] in replacements else token

    pattern = re.compile(r"(?<!\\)[Ee](?:[a-zA-Z_][a-zA-Z0-9_]*|_\{[^}]*\})?")
    return pattern.sub(repl, latex_str), replacements


def postprocess_E(expr: Any, replacements: Mapping[str, str]) -> Any:  # noqa: N802
    """Undo :func:`preprocess_E` on the symbols of a parsed expression."""
    if not replacements:
        return expr
    placeholder_to_char = {v: k for k, v in replacements.items()}
    subs = {}
    for symbol in expr.free_symbols:
        name = str(symbol)
        for placeholder, original in placeholder_to_char.items():
            if name.startswith(placeholder):
                subs[symbol] = Symbol(original + name[len(placeholder) :])
                break
    return expr.xreplace(subs)


def _latex2sympy(latex: str, substitutions: Mapping[Any, Any] | None = None) -> Any:
    """latex2sympy, retrying with ``E``/``e`` placeholders (see :func:`preprocess_E`)."""
    try:
        return latex2sympy(latex, substitutions) if substitutions is not None else latex2sympy(latex)
    except Exception:
        preprocessed, replacements = preprocess_E(latex)
        parsed = latex2sympy(preprocessed, substitutions) if substitutions is not None else latex2sympy(preprocessed)
        if isinstance(parsed, list):
            parsed = parsed.pop()
        return postprocess_E(parsed, replacements)


def parse_latex(response: str, symbols: Mapping[str, SymbolSpec], simplify: bool = False) -> str:
    """Parse LaTeX into a SymPy-syntax string, mapping task symbols to their codes.

    With ``simplify`` the expression is simplified first; otherwise it stays
    as close to the input as possible. ``\\pm``/``\\mp`` give both signs, as
    ``{a, b}``. Raises :class:`LatexParseError` if the response or a
    symbol's LaTeX can't be parsed.
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

    parsed_responses = set()
    for expression in responses:
        if expression.count("=") > 1:
            raise LatexParseError(f"An expression can contain at most one '=': {expression}", expression=expression)
        try:
            if "=" in expression:
                # Split equations here: PyPI's latex2sympy2 reads "x = 2" as an
                # assignment (returning 2), unlike the fork compareExpressions uses.
                lhs, rhs = (_latex2sympy(side, substitutions) for side in expression.split("="))
                parsed = Eq(lhs, rhs, evaluate=False)
            else:
                parsed = _latex2sympy(expression, substitutions)
        except Exception as e:
            raise LatexParseError(f"Failed to parse expression {expression!r}: {e}", expression=expression) from e
        if simplify:
            parsed = parsed.simplify()
        parsed_responses.add(str(parsed.subs(substitutions)))

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
