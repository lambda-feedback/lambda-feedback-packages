"""Helpers for the tags carried by expression-tree nodes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeAlias

from .tokens import ExprNode

TagRule: TypeAlias = Callable[[set[Any], set[Any]], set[Any]]
"""Combines two tag sets (see :func:`union_rule`, :func:`intersection_rule`)."""

TagCondition: TypeAlias = Callable[[set[Any]], bool]
"""Decides from a node's tags whether a tag helper applies."""


def union_rule(x: set[Any], y: set[Any]) -> set[Any]:
    return x | y


def intersection_rule(x: set[Any], y: set[Any]) -> set[Any]:
    return x & y


def _always(_tags: set[Any]) -> bool:
    return True


def inherit_tags(node: ExprNode, rule: TagRule = union_rule) -> set[Any]:
    """Tag handler: combine the children's tags with ``rule`` (union by default)."""
    if not node.children:
        return set()
    tags = set(node.children[0].tags)
    for child in node.children[1:]:
        tags = rule(tags, child.tags)
    return tags


def add_tag(node: ExprNode, tag: Any, rule: TagCondition = _always) -> ExprNode:
    """Add ``tag`` to the node if ``rule(node.tags)`` holds."""
    if rule(node.tags):
        node.tags.add(tag)
    return node


def remove_tag(node: ExprNode, tag: Any, rule: TagCondition = _always) -> ExprNode:
    """Remove ``tag`` from the node if present and ``rule(node.tags)`` holds."""
    if rule(node.tags):
        node.tags.discard(tag)
    return node


def replace_tag(node: ExprNode, old_tag: Any, new_tag: Any) -> ExprNode:
    """Swap ``old_tag`` for ``new_tag`` if the node has ``old_tag``."""
    if old_tag in node.tags:
        node.tags.discard(old_tag)
        node.tags.add(new_tag)
    return node
