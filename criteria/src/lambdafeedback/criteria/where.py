"""The substitutions of a ``where`` criterion, such as ``response = answer where a = 2; b = 3``."""

from __future__ import annotations

from lambdafeedback.slr_parsing import ExprNode

from .errors import CriteriaSyntaxError


def _substitution(node: ExprNode) -> tuple[str, str]:
    """``(name, expression)`` for a substitution such as ``a = 2``."""
    if node.label != "EQUALITY":
        raise CriteriaSyntaxError(f"`{node.content_string()}` is not a substitution such as `a = 2`.")
    name, expression = node.children
    return name.content_string(), expression.content_string()


def where_substitutions(substitutions: ExprNode) -> list[tuple[str, str]]:
    """``[(name, expression), ...]`` for the substitution part of a ``where`` criterion.

    ``substitutions`` is the second child of a ``WHERE`` node from
    :func:`.build_criteria_parser`: one ``EQUALITY`` or a ``SEPARATOR`` of
    them. The expressions are returned as text, for the caller to parse.
    Raises :class:`CriteriaSyntaxError` for any other relation, such as
    ``where x > 2``.
    """
    if substitutions.label == "SEPARATOR":
        return [_substitution(node) for node in substitutions.children]
    return [_substitution(substitutions)]
