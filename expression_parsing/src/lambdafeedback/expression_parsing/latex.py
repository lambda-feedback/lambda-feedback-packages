"""LaTeX output (SymPy → LaTeX) and input (LaTeX → SymPy string)."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator, Mapping
from string import ascii_letters
from typing import Any, Literal, TypeAlias

from latex2sympy2_extended import NormalizationConfig, normalize_latex
from latex2sympy2_extended.antlr_parser import PSLexer
from latex2sympy2_extended.latex2sympy2 import ConversionConfig, _Latex2Sympy
from sympy import Basic, FiniteSet, Float, Function, MatMul, Mul, Pow, Rational, Symbol, binomial
from sympy.core.function import AppliedUndef
from sympy.core.parameters import evaluate
from sympy.parsing.sympy_parser import implicit_multiplication_application, standard_transformations
from sympy.printing.latex import LatexPrinter

from ._safe_parse import TOO_DEEP_MESSAGE, check_input_length, safe_parse_expr
from ._scanning import CLOSING_BRACKETS, OPENING_BRACKETS, Match, find_matching_parenthesis, replace_matches
from .errors import LatexParseError
from .params import SymbolSpec
from .preprocessing import expand_plus_minus, split_equation
from .symbol_tables import MINUS_PLUS, PLUS_MINUS

# Symbol aliases are parsed with ``Symbol`` as the only name: an alias that
# needs anything more (a number, a function call) falls back to a plain name.
logger = logging.getLogger(__name__)

_ALIAS_NAMESPACE = {"Symbol": Symbol}
_ALIAS_TRANSFORMATIONS = (*standard_transformations, implicit_multiplication_application)

# A set, not the string: "" is in every string, and slicing past the end gives "".
_LETTERS = frozenset(ascii_letters)


def _replace_command(latex: str, command: str, replacement: str) -> str:
    """``command`` (e.g. ``\\pm``, but not the start of ``\\pmod``) and any whitespace after it as ``replacement``."""

    def find(text: str, index: int) -> Match | None:
        start = text.find(command, index)
        while start != -1 and text[start + len(command) : start + len(command) + 1] in _LETTERS:
            start = text.find(command, start + 1)
        if start == -1:
            return None
        after = start + len(command)
        return start, len(text) - len(text[after:].lstrip()), replacement

    return replace_matches(latex, find)


class _LatexPrinter(LatexPrinter):
    """SymPy's LaTeX printer, but printing logarithms with a base as ``\\log_{b}``."""

    def _print_log(self, expr: Any, exp: Any = None) -> str:
        if len(expr.args) > 1:
            log_not = rf"\log_{{{self._print(expr.args[1])}}}"
        else:
            log_not = r"\ln" if self._settings["ln_notation"] else r"\log"
        tex = rf"{log_not}{{\left({self._print(expr.args[0])} \right)}}"
        return rf"{tex}^{{{exp}}}" if exp is not None else tex


def extract_latex(symbol: str) -> str:
    """The math-mode part of a symbol's LaTeX string (the first one), or the whole string.

    Math mode is delimited by ``\\(...\\)``, ``$$...$$`` or ``$...$`` (any of
    the closers ends any opener) and doesn't span lines.
    """
    for start in range(len(symbol)):
        for opener in ("\\(", "$$", "$"):
            if not symbol.startswith(opener, start):
                continue
            body = start + len(opener)
            line_end = symbol.find("\n", body)
            line_end = len(symbol) if line_end == -1 else line_end
            # "$$" starts with "$", so the first "$" finds either.
            closers = [
                index for index in (symbol.find("\\)", body, line_end), symbol.find("$", body, line_end)) if index != -1
            ]
            if closers:
                return symbol[body : min(closers)]
    return symbol


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


def _find_placeholder(exp: str) -> str | None:
    """A letter not occurring in ``exp`` (``None`` if every candidate does)."""
    for char in "abcdfghjkoqrtvwxyzABCDFGHIJKLMNOPQRSTUVWXYZ":
        if char not in exp:
            return char
    return None


_ETokenKind: TypeAlias = Literal["command", "exponent", "letter"]


def _e_tokens(latex: str) -> Iterator[tuple[int, int, _ETokenKind]]:
    """``(start, end, kind)`` for each LaTeX command, ``E``/``e`` in scientific notation and other ``E``/``e``.

    ``kind`` is ``"command"`` (protected if it is ``\\gamma`` or ``\\Gamma``,
    otherwise left alone), ``"exponent"`` (``2E5``, ``1.5e-3``: the E is kept,
    as an upper-case E, which latex2sympy reads as an exponent) or ``"letter"``.
    """
    index = 0
    while index < len(latex):
        char = latex[index]
        if char == "\\" and latex[index + 1 : index + 2] in _LETTERS:
            end = index + 1
            while end < len(latex) and latex[end] in ascii_letters:
                end += 1
            yield index, end, "command"
            index = end
            continue
        if char in "Ee":
            exponent = latex[index + 1 : index + 2] in ("+", "-")
            follows_number = index > 0 and (latex[index - 1].isdecimal() or latex[index - 1] == ".")
            if follows_number and latex[index + 1 + exponent : index + 2 + exponent].isdecimal():
                yield index, index + 1, "exponent"
            else:
                yield index, index + 1, "letter"
        index += 1


# What a placeholder stands for, as written in LaTeX -> as a symbol name.
_PROTECTED = {"E": "E", "e": "e", r"\gamma": "gamma", r"\Gamma": "Gamma"}


def _protect_e_symbols(latex_str: str) -> tuple[str, dict[str, str]]:
    """Replace ``E``, ``e``, ``\\gamma`` and ``\\Gamma`` by placeholder letters, so they parse as plain symbols.

    latex2sympy2_extended reads them as constants or inconsistently: ``e`` as
    Euler's number, ``E`` after a digit as an exponent (``2E`` gives ``2``),
    and both ``\\gamma`` and ``\\Gamma`` as the Euler-Mascheroni constant (and
    fails on ``\\gamma_1``). As placeholders they are plain symbols, restored
    by :func:`_restore_e_symbols`, so whether they are constants is left to
    :func:`parse_expression` (``elementary_functions``, ``special_functions``),
    as for text input. Scientific notation (``2E5``) and other commands are
    left alone. Returns the modified string and ``{original: placeholder}``.
    """
    tokens = list(_e_tokens(latex_str))
    found = {latex_str[start:end] for start, end, kind in tokens if kind != "exponent"}
    replacements: dict[str, str] = {}
    for original in _PROTECTED:
        if original in found:
            placeholder = _find_placeholder(latex_str + "".join(replacements.values()))
            if placeholder:
                replacements[original] = placeholder

    pieces = []
    done = 0
    for start, end, kind in tokens:
        token = latex_str[start:end]
        pieces += [latex_str[done:start], "E" if kind == "exponent" else replacements.get(token, token)]
        done = end
    pieces.append(latex_str[done:])
    return "".join(pieces), replacements


def _restore_e_symbols(expr: Any, replacements: Mapping[str, str]) -> Any:
    """Undo :func:`_protect_e_symbols` on the symbols (and undefined functions) of a parsed expression."""
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


def _divide(top: Any, bottom: Any) -> Any:
    """``top / bottom``, unevaluated (``10/2`` stays ``10/2``)."""
    if getattr(top, "is_Matrix", False) or getattr(bottom, "is_Matrix", False):
        return MatMul(top, Pow(bottom, -1, evaluate=False), evaluate=False)
    return Mul(top, Pow(bottom, -1, evaluate=False), evaluate=False)


class _Converter(_Latex2Sympy):
    """latex2sympy2_extended's converter, building ``\\binom`` and division between numbers unevaluated.

    It built ``sympy.binomial`` evaluated, so ``\\binom{100000000}{50000000}``
    computed a 30-million-digit number, and divided two integers as a
    ``Rational`` (``\\frac{3}{6}`` gave ``1/2``, which a "written as" check
    can't tell from ``\\frac{1}{2}``). (Its other functions, ``factorial``
    included, are already unevaluated; a global ``evaluate(False)`` would
    change too much else.) This is the private class its ``latex2sympy()``
    wraps, so the dependency is pinned below 2.0.
    """

    def convert_binom(self, binom: Any) -> Any:
        return binomial(self.convert_expr(binom.upper), self.convert_expr(binom.lower), evaluate=False)

    def convert_mp(self, mp: Any) -> Any:
        if not (mp.DIV() or mp.CMD_DIV() or mp.COLON()):
            return super().convert_mp(mp)
        left, right = (mp.mp(0), mp.mp(1)) if hasattr(mp, "mp") else (mp.mp_nofunc(0), mp.mp_nofunc(1))
        return _divide(self.convert_mp(left), self.convert_mp(right))

    def convert_frac(self, frac: Any) -> Any:
        if _is_derivative_denominator(frac.lower):
            return super().convert_frac(frac)
        return _divide(self.convert_expr(frac.upper), self.convert_expr(frac.lower))


def _is_derivative_denominator(lower: Any) -> bool:
    """Whether a ``\\frac`` denominator is ``dx`` or ``\\partial x`` (latex2sympy2_extended's ``convert_frac`` test)."""
    if lower.start == lower.stop and lower.start.type == PSLexer.DIFFERENTIAL:
        return True
    start, stop = lower.getSourceInterval()
    return (
        stop - start == 1
        and lower.start.type == PSLexer.SYMBOL
        and lower.start.text == "\\partial"
        and lower.stop.type in (PSLexer.LETTER_NO_E, PSLexer.SYMBOL)
    )


# latex2sympy2_extended is tuned for grading free-form answers; keep it literal:
# case-sensitive symbols, "=" and "\in" as relations (never assignments), and
# only the basic LaTeX normalisation (\left/\right, \mathrm{d}, \dfrac, ...), not
# its answer extraction or units. (1.11 ignores interpret_as_mixed_fractions: it
# read 2\frac{1}{2} as a mixed number only because \frac{1}{2} was a Rational.
# With _Converter's unevaluated fractions, it is the product 2*1/2.)
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
    protected, replacements = _protect_e_symbols(latex)
    parsed = _Converter(config=_CONVERSION).parse(normalize_latex(protected, _NORMALISATION))
    if isinstance(parsed, list):
        parsed = parsed.pop()
    if isinstance(parsed, Basic):
        # Decimals come back as Floats (9.81 as 9.81000000000000); as rationals they are exact
        # and read back by parse_expression like the text it was given. Unevaluated, so
        # the rest of the expression stays as written (5 \cdot 7 stays 5*7).
        with evaluate(False):
            parsed = parsed.xreplace({number: Rational(str(number)) for number in parsed.atoms(Float)})
    return _restore_e_symbols(parsed, replacements)


MAX_LATEX_NESTING = 10
"""Deepest bracket nesting ``parse_latex`` accepts (``(``, ``[``, ``{`` combined).

latex2sympy2_extended's parser takes exponential time in the nesting depth
of brackets: 15 nested ``{`` take seconds and 20 take most of a minute.
Real answers rarely nest more than 3 or 4 deep.
"""


def _check_nesting(latex: str) -> None:
    depth = deepest = 0
    for char in latex:
        if char in OPENING_BRACKETS:
            depth += 1
            deepest = max(deepest, depth)
        elif char in CLOSING_BRACKETS:
            depth = max(depth - 1, 0)  # stray closers mustn't hide the nesting after them
    if deepest > MAX_LATEX_NESTING:
        raise LatexParseError(
            f"Brackets are nested {deepest} deep; at most {MAX_LATEX_NESTING} levels are supported.",
            expression=latex,
        )


def _symbol_substitutions(symbols: Mapping[str, SymbolSpec]) -> dict[Any, Symbol]:
    """``{parsed LaTeX or alias: Symbol(code)}`` for the task's symbols."""
    substitutions: dict[Any, Symbol] = {}
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
                    transformations=_ALIAS_TRANSFORMATIONS,
                    global_dict=_ALIAS_NAMESPACE,
                    local_dict={"E": Symbol("E")},
                )
            except Exception:
                parsed_alias = Symbol(alias)  # not an expression: use the alias as a plain name
            substitutions[parsed_alias] = Symbol(code)
    return substitutions


def parse_latex(response: str, symbols: Mapping[str, SymbolSpec], simplify: bool = False) -> str:
    """Parse LaTeX into a SymPy-syntax string, mapping task symbols to their codes.

    With ``simplify`` the expression is simplified first; otherwise it stays
    as close to the input as possible. ``\\pm``/``\\mp`` give both signs, as
    ``{a, b}``, and an equation gives ``lhs = rhs`` (each side simplified
    separately with ``simplify``). The result is text for
    :func:`parse_expression`. Raises :class:`LatexParseError` if the
    response or a symbol's LaTeX can't be parsed, or if brackets are nested
    more than :data:`MAX_LATEX_NESTING` deep.
    """
    check_input_length(response, LatexParseError)
    _check_nesting(response)
    substitutions = _symbol_substitutions(symbols)
    expanded = _replace_command(_replace_command(response, "\\pm", PLUS_MINUS), "\\mp", MINUS_PLUS)
    responses = list(dict.fromkeys(expand_plus_minus(expanded)))

    def text(parsed: Any) -> str:
        return str((parsed.simplify() if simplify else parsed).subs(substitutions))

    parsed_responses = set()
    for expression in responses:
        sides = split_equation(expression, LatexParseError)
        try:
            if len(sides) == 2:
                # An equation is written "lhs = rhs", as parse_expression reads it, with each
                # side parsed separately ("Eq(x, 2)" would not survive parse_expression with
                # elementary_functions, where the E of Eq is Euler's number).
                parsed_responses.add(" = ".join(text(_latex2sympy(side)) for side in sides))
                continue
            parsed = _latex2sympy(expression)
            # A comma-separated list ("1, 2") is several answers, like "{1, 2}" in text;
            # merged with the ± expansion rather than nested in it.
            parsed_responses.update(text(item) for item in (parsed.args if isinstance(parsed, FiniteSet) else [parsed]))
        except RecursionError as e:
            raise LatexParseError(TOO_DEEP_MESSAGE, expression=expression) from e
        except Exception as e:
            raise LatexParseError(f"Failed to parse expression {expression!r}: {e}", expression=expression) from e

    result = parsed_responses.pop() if len(parsed_responses) < 2 else "{" + ", ".join(sorted(parsed_responses)) + "}"
    logger.debug("parse_latex %r -> %r", response, result)
    return result


def sanitise_latex(response: str) -> str:
    """Remove whitespace, turn ``~`` into spaces and unwrap ``\\mathrm{...}`` / ``\\text{...}``.

    (units has its own, more lenient unwrapping for quantity previews: ``units.text._unwrap_upright``.)
    """
    response = "".join(response.split()).replace("~", " ")
    for wrapper in (r"\mathrm", r"\text"):
        response = replace_matches(response, _wrapped_content(wrapper))
    return response


def _wrapped_content(wrapper: str) -> Callable[[str, int], Match | None]:
    """Finder for :func:`replace_matches`: ``wrapper{...}`` as its content; raises if the brace is unclosed."""

    def find(text: str, index: int) -> Match | None:
        start = text.find(wrapper + "{", index)
        if start < 0:
            return None
        end = find_matching_parenthesis(text, start + 1, delimiters=("{", "}"))
        if end < 0:
            raise LatexParseError(f"Unclosed {wrapper}{{...}} in {text!r}.", expression=text)
        return start, end + 1, text[start + len(wrapper) + 1 : end]

    return find
