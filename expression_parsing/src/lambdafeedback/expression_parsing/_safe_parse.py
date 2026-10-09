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
import re
from collections.abc import Mapping
from typing import Any

import sympy
from sympy import Abs, Basic, Max, Min
from sympy.parsing.sympy_parser import eval_expr, evaluateFalse, stringify_expr

from .errors import ExpressionParsingError

# Plain Python functions (not Basic subclasses) that are part of the maths.
_MATH_FUNCTIONS = ("sqrt", "root", "cbrt", "real_root", "diff", "integrate", "summation", "product", "limit")


def _math_namespace() -> dict[str, Any]:
    namespace: dict[str, Any] = {}
    for name in sympy.__all__:
        obj = getattr(sympy, name)
        if isinstance(obj, Basic) or (isinstance(obj, type) and issubclass(obj, Basic)):
            namespace[name] = obj
    namespace.update({name: getattr(sympy, name) for name in _MATH_FUNCTIONS})
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
_NUMBER_STRING = re.compile(r"[0-9._eE+\-/]+")


def _allowed_string(constructor: str, value: str) -> bool:
    if constructor in _NAME_CONSTRUCTORS:
        return value.isidentifier()
    return constructor in _NUMBER_CONSTRUCTORS and _NUMBER_STRING.fullmatch(value) is not None


MAX_NUMBER_DIGITS = 1000
"""Most digits a number may have (not counting its exponent)."""
MAX_NUMBER_EXPONENT = 1000
"""Largest exponent (``1e1000``) a number may have, of either sign."""

_EXPONENT = re.compile(r"[eE]([+-]?)(\d+)")


def _number_size_error(number: str, expr: str) -> ExpressionParsingError | None:
    """Why ``number`` (a literal's text) is too large for SymPy to handle in reasonable time, if it is.

    ``Float('1e999999')`` takes minutes (``Rational`` of it is an integer too
    long for ``str()``), and so does a mantissa of 100000 digits.
    """
    mantissa, _, exponent = number.partition("e") if "e" in number else number.partition("E")
    digits = sum(character.isdigit() for character in mantissa)
    if digits > MAX_NUMBER_DIGITS:
        return ExpressionParsingError(
            f"A number has {digits} digits; at most {MAX_NUMBER_DIGITS} are allowed.", expression=expr
        )
    match = _EXPONENT.fullmatch("e" + exponent) if exponent else None
    if match is not None:
        magnitude = match.group(2).lstrip("0")
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
            raise ExpressionParsingError(
                f"A number has too many digits; at most {MAX_NUMBER_DIGITS} are allowed.", expression=expr
            ) from e
        raise ExpressionParsingError(f"Invalid syntax in {expr!r}", expression=expr) from e

    string_arguments: dict[int, str] = {}  # id(argument node) -> constructor name
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, int)
            and node.value.bit_length() > MAX_NUMBER_DIGITS * 3.33  # log2(10): about that many decimal digits
        ):
            raise ExpressionParsingError(
                f"A number has too many digits; at most {MAX_NUMBER_DIGITS} are allowed.", expression=expr
            )
        if not isinstance(node, _ALLOWED_NODES):
            raise reject(type(node).__name__)
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise reject(f"The name {node.id!r}")
        if isinstance(node, ast.keyword) and (node.arg is None or node.arg.startswith("_")):
            raise reject("This keyword argument")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and len(node.args) == 1 and not node.keywords:
            string_arguments[id(node.args[0])] = node.func.id
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
        return next((char for char in value if not _NUMBER_STRING.fullmatch(char)), None)
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
    compiled = compile(evaluateFalse(code), "<string>", "eval") if not evaluate else code
    return eval_expr(compiled, local_dict, namespace)
