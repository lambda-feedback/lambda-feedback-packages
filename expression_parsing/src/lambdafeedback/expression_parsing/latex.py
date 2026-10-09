"""LaTeX output (SymPy → LaTeX) and input (LaTeX → SymPy string)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from latex2sympy2_extended import NormalizationConfig, latex2sympy
from latex2sympy2_extended.latex2sympy2 import ConversionConfig
from sympy import Basic, FiniteSet, Float, Function, Rational, Symbol
from sympy.core.function import AppliedUndef
from sympy.core.parameters import evaluate
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


# A LaTeX command (protected if it is \gamma or \Gamma, otherwise left alone),
# scientific notation (2E5, 1.5e-3: the E is kept, as an upper-case E, which
# latex2sympy reads as an exponent), or any other E or e.
_E_OR_COMMAND = re.compile(r"(\\[A-Za-z]+)|(?<=[\d.])([Ee])(?=[+-]?\d)|([Ee])")

# What a placeholder stands for, as written in LaTeX -> as a symbol name.
_PROTECTED = {"E": "E", "e": "e", r"\gamma": "gamma", r"\Gamma": "Gamma"}


def preprocess_E(latex_str: str) -> tuple[str, dict[str, str]]:  # noqa: N802
    """Replace ``E``, ``e``, ``\\gamma`` and ``\\Gamma`` by placeholder letters, so they parse as plain symbols.

    latex2sympy2_extended reads them as constants or inconsistently: ``e`` as
    Euler's number, ``E`` after a digit as an exponent (``2E`` gives ``2``),
    and both ``\\gamma`` and ``\\Gamma`` as the Euler-Mascheroni constant (and
    fails on ``\\gamma_1``). As placeholders they are plain symbols, restored
    by :func:`postprocess_E`, so whether they are constants is left to
    :func:`parse_expression` (``elementary_functions``, ``special_functions``),
    as for text input. Scientific notation (``2E5``) and other commands are
    left alone. Returns the modified string and ``{original: placeholder}``.
    """
    found = {match.group(3) or match.group(1) for match in _E_OR_COMMAND.finditer(latex_str)}
    replacements: dict[str, str] = {}
    for original in _PROTECTED:
        if original in found:
            placeholder = find_placeholder(latex_str + "".join(replacements.values()))
            if placeholder:
                replacements[original] = placeholder

    def repl(match: re.Match[str]) -> str:
        command, exponent, letter = match.groups()
        if command:
            return replacements.get(command, command)
        if exponent:
            return "E"
        return replacements.get(letter, letter)

    return _E_OR_COMMAND.sub(repl, latex_str), replacements


def postprocess_E(expr: Any, replacements: Mapping[str, str]) -> Any:  # noqa: N802
    """Undo :func:`preprocess_E` on the symbols (and undefined functions) of a parsed expression."""
    if not replacements:
        return expr
    restore = str.maketrans({placeholder: _PROTECTED[original] for original, placeholder in replacements.items()})
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


# latex2sympy2_extended is tuned for grading free-form answers; keep it literal:
# case-sensitive symbols, 2\frac{1}{2} read as a mixed number, "=" and "\in"
# as relations (never assignments), and only the basic LaTeX normalisation
# (\left/\right, \mathrm{d}, \dfrac, ...), not its answer extraction or units.
_CONVERSION = ConversionConfig(
    lowercase_symbols=False,
    interpret_as_mixed_fractions=False,
    interpret_simple_eq_as_assignment=False,
    interpret_contains_as_eq=False,
)
_NORMALISATION = NormalizationConfig(
    basic_latex=True, units=False, malformed_operators=False, nits=False, boxed="none", equations=False
)


def _latex2sympy(latex: str) -> Any:
    """latex2sympy2_extended with ``E``/``e``/``\\gamma`` as plain symbols and decimals as exact rationals."""
    protected, replacements = preprocess_E(latex)
    parsed = latex2sympy(protected, normalization_config=_NORMALISATION, conversion_config=_CONVERSION)
    if isinstance(parsed, list):
        parsed = parsed.pop()
    if isinstance(parsed, Basic):
        # Decimals come back as Floats (9.81 as 9.81000000000000); as rationals they are exact
        # and read back by parse_expression like the text it was given. Unevaluated, so
        # the rest of the expression stays as written (5 \cdot 7 stays 5*7).
        with evaluate(False):
            parsed = parsed.xreplace({number: Rational(str(number)) for number in parsed.atoms(Float)})
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

    def text(parsed: Any) -> str:
        return str((parsed.simplify() if simplify else parsed).subs(substitutions))

    parsed_responses = set()
    for expression in responses:
        if expression.count("=") > 1:
            raise LatexParseError(f"An expression can contain at most one '=': {expression}", expression=expression)
        try:
            if "=" in expression:
                # An equation is written "lhs = rhs", as parse_expression reads it, with each
                # side parsed separately ("Eq(x, 2)" would not survive parse_expression with
                # elementary_functions, where the E of Eq is Euler's number).
                parsed_responses.add(" = ".join(text(_latex2sympy(side)) for side in expression.split("=")))
                continue
            parsed = _latex2sympy(expression)
            # A comma-separated list ("1, 2") is several answers, like "{1, 2}" in text;
            # merged with the ± expansion rather than nested in it.
            parsed_responses.update(text(item) for item in (parsed.args if isinstance(parsed, FiniteSet) else [parsed]))
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
