"""Splitting a quantity's parse tree into its value and its unit."""

from __future__ import annotations

import logging

from lambdafeedback.slr_parsing import GROUP_LABEL, ExprNode, TagHandler

from .errors import QuantityParseError
from .parser import Label
from .tags import QuantityTag

logger = logging.getLogger(__name__)

MAX_UNIT_EXPONENT = 100
"""Largest exponent a unit may have (``m^100``), of either sign."""

_EXPONENT_LABELS = frozenset({Label.NUMBER, GROUP_LABEL, Label.SOLIDUS, Label.PRODUCT, Label.SPACE})


def _exponent_problem(unit: ExprNode) -> str | None:
    """Why the exponents in a unit can't be used, if they can't.

    An exponent must be numbers combined with brackets, ``*``, ``/`` or spaces,
    and stay within :data:`MAX_UNIT_EXPONENT`. Otherwise converting the unit
    could build an enormous number: ``km^(10^10)`` has the factor
    ``1000^(10^10)``, and ``km^Pa^km`` (a unit as an exponent) hung.
    """
    stack = [unit]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.label != Label.POWER:
            continue
        bound = 1.0  # at least the exponent's magnitude: the product of its numbers' sizes
        exponent_nodes = [node.children[1]]
        while exponent_nodes:
            part = exponent_nodes.pop()
            if part.label not in _EXPONENT_LABELS:
                return f"A unit's exponent must be a number, not {part.original_string()!r}."
            if part.label == Label.NUMBER:
                bound *= max(1.0, abs(float(part.content)))
            exponent_nodes.extend(part.children)
        if bound > MAX_UNIT_EXPONENT:
            return f"The exponent of {node.original_string()!r} is too large; at most {MAX_UNIT_EXPONENT} is allowed."
    return None


def _has_stray_number(node: ExprNode) -> bool:
    """Whether a unit subtree contains a number outside an exponent or the ``1`` of ``1/unit``.

    Groups are not looked into: a bracketed group is kept whole (see
    :func:`_rotate_until_root_is_split`).
    """
    stack = [node]  # iterative: a long unit such as m*m*...*m is a deep tree
    while stack:
        node = stack.pop()
        if node.label == Label.NUMBER:
            return True
        if node.label == GROUP_LABEL:
            continue
        if node.label == Label.POWER:
            stack.append(node.children[0])
        elif node.label == Label.SOLIDUS and node.children[0].label == Label.NUMBER and node.children[0].content == "1":
            stack.append(node.children[1])
        else:
            stack.extend(node.children)
    return False


def _rotate(root: ExprNode, right: bool, tag_handler: TagHandler) -> ExprNode:
    """Tree rotation at ``root``, to the right (the left child becomes the root) or to the left.

    Returns the new root.
    """
    # The child that becomes the root, and which of its children moves across to the old root.
    pivot, inner = (0, -1) if right else (1, 0)
    new_root = root.children[pivot]
    # Only binary nodes can be rotated; groups (one child) are atomic.
    if len(new_root.children) < 2:
        raise QuantityParseError(f"Cannot rotate {'right' if right else 'left'}.")
    root.children[pivot] = new_root.children[inner]
    new_root.children[inner] = root
    # Retagging can change the nodes too: in strict mode it strips the unit tag from a juxtaposition's children.
    root.tags = tag_handler(root)
    new_root.tags = tag_handler(new_root)
    return new_root


def _rotate_until_root_is_split(root: ExprNode, tag_handler: TagHandler) -> ExprNode:
    """Rotate ``SPACE`` roots until the root separates value (left) from unit (right); returns the new root.

    Only binary nodes are rotated into: a group (e.g. ``(2 m)``) is kept whole.
    A rotation followed by the opposite one would undo it, so a change of
    direction means there is no split (e.g. ``5 m/s x``, a unit between
    value parts).
    """
    previous: bool | None = None  # the direction of the last rotation (True: right)
    while root.label == Label.SPACE:
        left, right = root.children
        if QuantityTag.UNIT not in root.tags and len(right.children) > 1:
            rotate_right = False
        elif QuantityTag.UNIT in left.tags and len(left.children) > 1:
            rotate_right = True
        else:
            return root
        if previous is not None and rotate_right != previous:
            raise QuantityParseError(f"Cannot separate the value from the unit in {root.original!r}.")
        logger.debug("rotate %s to split value from unit", "right" if rotate_right else "left")
        root = _rotate(root, rotate_right, tag_handler)
        previous = rotate_right
    return root


def split_value_and_unit(root: ExprNode, tag_handler: TagHandler) -> tuple[ExprNode, ExprNode | None, ExprNode | None]:
    """The root after rotating it to separate value from unit, the value and the unit.

    See :func:`_rotate_until_root_is_split`. Raises :class:`QuantityParseError` if
    they can't be separated, or the unit's exponents can't be used.
    """
    root = _rotate_until_root_is_split(root, tag_handler)
    value: ExprNode | None = None
    unit: ExprNode | None = None
    if (
        root.label == Label.SPACE
        and QuantityTag.UNIT not in root.children[0].tags
        and QuantityTag.UNIT in root.children[1].tags
    ):
        value, unit = root.children
    elif QuantityTag.UNIT in root.tags:
        unit = root
    else:
        value = root
    if logger.isEnabledFor(logging.DEBUG):
        value_text = None if value is None else value.content_string()
        unit_text = None if unit is None else unit.content_string()
        logger.debug("split %r into value %r and unit %r", root.original, value_text, unit_text)
    # e.g. "2 m 3 s" or "1 hour 30 minutes": the unit would contain a number.
    if unit is not None and _has_stray_number(unit):
        raise QuantityParseError(f"Cannot separate the value from the unit in {root.original!r}.")
    if unit is not None and (problem := _exponent_problem(unit)) is not None:
        raise QuantityParseError(problem)
    return root, value, unit
