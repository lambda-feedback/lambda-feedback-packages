"""A ``sympy.parse_expr`` that only evaluates mathematical expressions.

``parse_expr`` turns its input into Python code and ``eval``s it. Its default
namespace holds all of SymPy plus Python's builtin functions (``open``,
``__import__``, ``getattr``, ...), so learner input could run arbitrary code.
:func:`safe_parse_expr` runs the same pipeline (``stringify_expr``, then
``evaluateFalse``, then ``eval_expr``) with two guards in between:

* the generated code is checked against an allowlist of syntax: arithmetic,
  comparisons, calls of plain names, numbers and tuple/list/set literals.
  Attribute access, subscripts, lambdas, comprehensions and the like are
  rejected, and a string literal is only allowed as the single argument of
  the constructors SymPy's own transformations generate, holding a name
  (``Symbol('x')``) or a number (``Float('1.5')``). SymPy functions
  ``sympify`` string arguments with its unrestricted default namespace, so
  no other string may reach them;
* the code is evaluated in :data:`MATH_NAMESPACE`: SymPy's mathematical
  objects and classes, no builtins, and none of its printing, plotting,
  code-generation or ``sympify`` helpers.
"""

from __future__ import annotations

import ast
import math
from collections.abc import Mapping
from typing import Any

import sympy
from sympy import (
    Abs,
    Add,
    Basic,
    Function,
    Integral,
    Limit,
    Max,
    Min,
    Mod,
    Mul,
    Pow,
    Product,
    Rational,
    Sum,
    arg,
    ceiling,
    conjugate,
    exp,
    floor,
    frac,
    im,
    log,
    re,
    sign,
)
from sympy.core.function import AppliedUndef, FunctionClass
from sympy.core.operations import AssocOp
from sympy.core.relational import Relational
from sympy.functions.elementary.hyperbolic import HyperbolicFunction, InverseHyperbolicFunction
from sympy.functions.elementary.trigonometric import InverseTrigonometricFunction, TrigonometricFunction
from sympy.parsing.sympy_parser import eval_expr, evaluateFalse, stringify_expr

from .errors import ExpressionParsingError

# Plain Python functions (not Basic subclasses) that are part of the maths.
_MATH_FUNCTIONS = ("sqrt", "root", "cbrt", "real_root", "diff")
# Functions that work out an integral, sum, product or limit, read as the unevaluated
# object instead: working one out can take practically forever (sum(k!, (k, 1, 10**6))).
_UNEVALUATED_FUNCTIONS = {"integrate": Integral, "summation": Sum, "product": Product, "limit": Limit}


def _math_namespace() -> dict[str, Any]:
    namespace: dict[str, Any] = {}
    for name in sympy.__all__:
        obj = getattr(sympy, name)
        if isinstance(obj, Basic) or (isinstance(obj, type) and issubclass(obj, Basic)):
            namespace[name] = obj
    namespace.update({name: getattr(sympy, name) for name in _MATH_FUNCTIONS})
    namespace.update(_UNEVALUATED_FUNCTIONS)
    # The spellings parse_expr's default namespace provides via builtins.
    namespace.update({"abs": Abs, "max": Max, "min": Min})
    namespace["__builtins__"] = {}
    return namespace


MATH_NAMESPACE: Mapping[str, Any] = _math_namespace()
"""Names available to parsed expressions (beyond the caller's ``local_dict``)."""

# The constructors SymPy's transformations call with a string, and what that
# string may contain. Number('3') (from split_symbols_custom) sympifies its
# argument, so the check is on the content, not just the call.
_NAME_CONSTRUCTORS = frozenset({"Symbol", "Function"})
_NUMBER_CONSTRUCTORS = frozenset({"Number", "Integer", "Float", "Rational"})
_NUMBER_CHARACTERS = frozenset("0123456789._eE+-/")


def _allowed_string(constructor: str, value: str) -> bool:
    if constructor in _NAME_CONSTRUCTORS:
        return value.isidentifier()
    return constructor in _NUMBER_CONSTRUCTORS and value != "" and set(value) <= _NUMBER_CHARACTERS


MAX_NUMBER_DIGITS = 1000
"""Most digits a number may have (not counting its exponent)."""
MAX_NUMBER_EXPONENT = 1000
"""Largest exponent (``1e1000``) a number may have, of either sign."""

_TOO_MANY_DIGITS = 10**MAX_NUMBER_DIGITS  # the smallest integer with one digit too many


def _too_many_digits(expr: str, digits: int | None = None) -> ExpressionParsingError:
    count = f"{digits} digits" if digits is not None else "too many digits"
    return ExpressionParsingError(f"A number has {count}; at most {MAX_NUMBER_DIGITS} are allowed.", expression=expr)


def _number_size_error(number: str, expr: str) -> ExpressionParsingError | None:
    """Why ``number`` (a literal's text) is too large for SymPy to handle in reasonable time, if it is.

    ``Float('1e999999')`` takes minutes (``Rational`` of it is an integer too
    long for ``str()``), and so does a mantissa of 100000 digits.
    """
    mantissa, _, exponent = number.partition("e") if "e" in number else number.partition("E")
    digits = sum(character.isdigit() for character in mantissa)
    if digits > MAX_NUMBER_DIGITS:
        return _too_many_digits(expr, digits)
    exponent_digits = exponent[1:] if exponent[:1] in ("+", "-") else exponent
    if exponent_digits.isdecimal():
        magnitude = exponent_digits.lstrip("0")
        if len(magnitude) > len(str(MAX_NUMBER_EXPONENT)) or int(magnitude or 0) > MAX_NUMBER_EXPONENT:
            return ExpressionParsingError(
                f"The exponent of {number[:30]!r} is out of range; at most ±{MAX_NUMBER_EXPONENT} is allowed.",
                expression=expr,
            )
    return None


_ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.Call,
    ast.keyword,
    ast.Name,
    ast.Constant,
    ast.Tuple,
    ast.List,
    ast.Set,
    ast.expr_context,
    ast.operator,
    ast.unaryop,
    ast.boolop,
    ast.cmpop,
)


def _check_code(code: str, expr: str) -> None:
    """Raise :class:`ExpressionParsingError` unless ``code`` only uses allowed syntax."""

    def reject(what: str) -> ExpressionParsingError:
        return ExpressionParsingError(f"{what} is not allowed in a mathematical expression: {expr!r}", expression=expr)

    try:
        tree = ast.parse(code, mode="eval")
    except SyntaxError as e:
        if "integer string conversion" in str(e):  # an integer literal over Python's 4300-digit limit
            raise _too_many_digits(expr) from e
        raise ExpressionParsingError(f"Invalid syntax in {expr!r}", expression=expr) from e

    # id(argument node) -> constructor name, for every single-argument call of a plain name.
    # Collected up front so the check below doesn't depend on the order ast.walk visits nodes in.
    string_arguments = {
        id(node.args[0]): node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and len(node.args) == 1 and not node.keywords
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, int) and abs(node.value) >= _TOO_MANY_DIGITS:
            raise _too_many_digits(expr)
        if not isinstance(node, _ALLOWED_NODES):
            raise reject(type(node).__name__)
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise reject(f"The name {node.id!r}")
        if isinstance(node, ast.keyword) and (node.arg is None or node.arg.startswith("_")):
            raise reject("This keyword argument")
        if isinstance(node, ast.Constant) and not isinstance(node.value, int | float | complex | bool | None):
            constructor = string_arguments.get(id(node))
            if not (isinstance(node.value, str) and constructor and _allowed_string(constructor, node.value)):
                character = _unreadable_character(constructor, node.value)
                if character is not None:
                    # SymPy wrapped a character Python can't read (e.g. '−', '×', the '²' of 'x²').
                    raise ExpressionParsingError(f"Unrecognised character {character!r} in {expr!r}", expression=expr)
                raise reject("A string or other literal")
            if constructor in _NUMBER_CONSTRUCTORS and (error := _number_size_error(node.value, expr)) is not None:
                raise error


def _unreadable_character(constructor: str | None, value: object) -> str | None:
    """For a symbol name or number SymPy generated, the first character that makes it invalid."""
    if not isinstance(value, str):
        return None
    if constructor in _NAME_CONSTRUCTORS:
        return next((char for char in value if not f"a{char}".isidentifier()), None)
    if constructor in _NUMBER_CONSTRUCTORS:
        return next((char for char in value if char not in _NUMBER_CHARACTERS), None)
    return None


def safe_parse_expr(
    expr: str,
    *,
    transformations: tuple[Any, ...],
    local_dict: dict[str, Any],
    global_dict: Mapping[str, Any] = MATH_NAMESPACE,
    evaluate: bool = True,
) -> Any:
    """``sympy.parse_expr`` restricted to mathematical expressions (see the module docstring).

    ``global_dict`` must not contain builtins; a namespace without a
    ``__builtins__`` entry gets an empty one.
    """
    namespace = {"__builtins__": {}, **global_dict}
    code = stringify_expr(expr, local_dict, namespace, transformations)
    _check_code(code, expr)
    if evaluate:
        return eval_expr(code, local_dict, namespace)
    tree = _UnevaluatedCalls({**namespace, **local_dict}).visit(evaluateFalse(code))
    return eval_expr(compile(ast.fix_missing_locations(tree), "<string>", "eval"), local_dict, namespace)


# Classes (not FunctionClasses) that compute when constructed unless told not to.
_EVALUATING_CLASSES = (Pow, AssocOp, Relational)


class _UnevaluatedCalls(ast.NodeTransformer):
    """Add ``evaluate=False`` to every call of a SymPy function class or operator class.

    ``evaluateFalse`` only does so for a fixed list (trigonometric, ``exp``,
    ``log``, ...), so ``factorial``, ``binomial`` and the number-theory
    functions still computed: ``10000000!`` took minutes, and ``100000!`` gave
    an integer too long to print. Operator classes called by name computed
    too: ``Pow(9, Pow(9, 9))`` never finished.
    """

    def __init__(self, names: Mapping[str, Any]) -> None:
        self.names = names

    def visit_Call(self, node: ast.Call) -> ast.Call:
        self.generic_visit(node)
        target = self.names.get(node.func.id) if isinstance(node.func, ast.Name) else None
        # Function itself (Function('f')) is a FunctionClass too, but it creates functions rather than evaluating.
        is_function = isinstance(target, FunctionClass) and target is not Function
        is_operator = isinstance(target, type) and issubclass(target, _EVALUATING_CLASSES)
        if (is_function or is_operator) and not any(keyword.arg == "evaluate" for keyword in node.keywords):
            node.keywords.append(ast.keyword(arg="evaluate", value=ast.Constant(False)))
        return node


MAX_INPUT_LENGTH = 10_000
"""Longest text :func:`~lambdafeedback.expression_parsing.parse_expression` and ``parse_latex`` read, in characters."""

TOO_DEEP_MESSAGE = "The expression is too long or too deeply nested."
"""The message when parsing exceeds Python's recursion limit (a sum of hundreds of terms, say)."""


def check_input_length(text: str, error: type[ExpressionParsingError] = ExpressionParsingError) -> None:
    """Raise ``error`` if ``text`` is longer than :data:`MAX_INPUT_LENGTH`: a bound on parsing time."""
    if len(text) > MAX_INPUT_LENGTH:
        raise error(
            f"The expression is too long: {len(text)} characters; at most {MAX_INPUT_LENGTH} are allowed.",
            expression=text[:100],
        )


MAX_SIMPLIFY_POWER = 500
"""Largest power a sum containing symbols may be raised to when simplifying (``(x+1)**500``)."""

# Functions whose value is no larger than their arguments' (or not an exact number at all).
_BOUNDED_FUNCTIONS = (Abs, sign, re, im, conjugate, floor, ceiling, frac, Mod)
_INEXACT_FUNCTIONS = (
    TrigonometricFunction,
    InverseTrigonometricFunction,
    HyperbolicFunction,
    InverseHyperbolicFunction,
    exp,
    log,
    arg,
    AppliedUndef,
)


def check_evaluation_cost(expr: Basic, text: str) -> None:
    """Raise :class:`ExpressionParsingError` if evaluating the unevaluated ``expr`` could take practically forever.

    Evaluating builds exact numbers, so ``9**9**9`` or ``factorial(10**8)``
    never finishes, and functions such as ``bell`` or ``primepi`` compute
    from their argument. Any exact number evaluation could build is bounded
    by :data:`MAX_NUMBER_DIGITS` digits, like a number the learner types. A
    sum containing symbols may be raised to at most :data:`MAX_SIMPLIFY_POWER`:
    simplifying ``(x+1)**1000`` takes seconds.

    This bounds evaluation, not SymPy's symbolic algorithms: simplifying can
    still be slow on large or contrived expressions.
    """
    try:
        _log_size(expr)
    except _TooCostlyError as e:
        raise ExpressionParsingError(e.template.format(text=repr(text)), expression=text) from None


class _TooCostlyError(Exception):
    """Raised by :func:`_log_size`; ``template`` is the message, with ``{text}`` for the expression."""

    def __init__(self, template: str) -> None:
        super().__init__(template)
        self.template = template


def _magnitude(log_size: float) -> float:
    """The largest value with this ``log10`` size."""
    return math.inf if log_size > 300 else float(10**log_size)


def _log_size(node: Basic) -> float:
    """At least ``log10`` of the largest exact number (numerator or denominator) evaluating ``node`` builds.

    Symbols and inexact values (floats, ``pi``, ``sin(x)``) count as 1: their
    powers don't build exact numbers.
    """
    if isinstance(node, Rational):
        # Exact for small numbers: an overestimate here compounds through nested powers.
        return math.log10(max(abs(node.p), node.q))
    sizes = [_log_size(argument) for argument in node.args]
    largest = max(sizes, default=0.0)
    if isinstance(node, Add):
        size = largest + math.log10(len(sizes) or 1)
    elif isinstance(node, Mul):
        size = sum(sizes)
    elif isinstance(node, Pow):
        base, exponent = sizes
        power = _magnitude(exponent)
        if power > MAX_SIMPLIFY_POWER and node.base.free_symbols and node.base.has(Add):
            raise _TooCostlyError(
                f"A sum is raised to too large a power to simplify in {{text}}; "
                f"at most {MAX_SIMPLIFY_POWER} is allowed."
            )
        size = base * power if base else 0.0
    elif isinstance(node, _BOUNDED_FUNCTIONS) or not isinstance(node, Function):
        size = largest  # also symbols, relations, tuples, Max/Min, unevaluated sums and integrals
    elif isinstance(node, _INEXACT_FUNCTIONS):
        size = 0.0
    else:
        # factorial, binomial, bell, fibonacci, primepi, zeta, ...: computed from the
        # argument, with values of up to about n*log10(n) digits (n! has fewer).
        n = _magnitude(largest)
        size = n * math.log10(2 * n)
    if size > MAX_NUMBER_DIGITS:
        raise _TooCostlyError(
            f"Evaluating {{text}} builds a number of more than {MAX_NUMBER_DIGITS} digits; "
            f"at most {MAX_NUMBER_DIGITS} are allowed."
        )
    return size
