"""Reduction actions: build the output tree when a production is reduced.

Every action has the signature ``action(production, output, tag_handler) ->
output`` (see :data:`~lambdafeedback.slr_parsing.grammar.Action`); the
functions taking parameters (``group``, ``operate``, ...) return one.

Only actions that build a new node (``create_node``, ``group``, ``operate``,
``infix``, ``insert_infix``) run the tag handler. Actions that change an
existing node in place (``append``, ``append_last``, ``join``, ``relabel``,
``flatten``) leave its tags as they were.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .grammar import Action, TagHandler, TokenProduction
from .tokens import ExprNode, Token, traverse_group, traverse_infix


def _as_nodes(items: list[Any], tag_handler: TagHandler | None) -> list[ExprNode]:
    return [item if isinstance(item, ExprNode) else ExprNode(item, [], tag_handler=tag_handler) for item in items]


def proceed(_production: TokenProduction, output: list[Any], _tag_handler: TagHandler | None) -> list[Any]:
    """Leave the output unchanged."""
    return output


def _body_start(production: TokenProduction, output: list[Any]) -> int:
    """Index in ``output`` of the first item of the production body.

    Slicing from an explicit index avoids ``output[-0:]``/``output[:1 - 1]``,
    which select the whole stack (or none of it) for a one-symbol body.
    """
    return len(output) - len(production[1])


def append(production: TokenProduction, output: list[Any], tag_handler: TagHandler | None) -> list[Any]:
    """Append the rest of the body's items as children of its first item."""
    first = _body_start(production, output)
    output[first].children += output[first + 1 :]
    return output[: first + 1]


def append_last(production: TokenProduction, output: list[Any], _tag_handler: TagHandler | None) -> list[Any]:
    """Append the body's last item as a child of its first; drop the items between."""
    first = _body_start(production, output)
    if first < len(output) - 1:
        output[first].children.append(output[-1])
    return output[: first + 1]


def join(production: TokenProduction, output: list[Any], _tag_handler: TagHandler | None) -> list[Any]:
    """Merge the body's items into its first item, relabelled as the production head."""
    first = _body_start(production, output)
    content = [item.content_string() if isinstance(item, ExprNode) else item.content for item in output[first:]]
    joined_end = output[-1].end
    output = output[: first + 1]
    output[-1].label = production[0].label
    output[-1].content = "".join(content)
    output[-1].end = joined_end
    return output


def create_node(_production: TokenProduction, output: list[Any], tag_handler: TagHandler | None) -> list[Any]:
    """Wrap the last item in a new tree node."""
    output.append(ExprNode(output.pop(), [], tag_handler=tag_handler))
    return output


def relabel(production: TokenProduction, output: list[Any], _tag_handler: TagHandler | None) -> list[Any]:
    """Relabel the last item as the production head.

    A tree node keeps its children and tags; a plain token is replaced by a
    relabelled copy.
    """
    a = output[-1]
    if isinstance(a, ExprNode):
        a.label = production[0].label
    else:
        output[-1] = Token(production[0].label, a.content, a.original, a.start, a.end)
    return output


def group(number_of_elements: int, empty: bool = False, delimiters: Sequence[str] = ("", "")) -> Action:
    """Action wrapping the last ``number_of_elements`` items in a ``GROUP`` node.

    With ``empty=False`` the items are enclosed by delimiter tokens in the
    body, which become the group's content. With ``empty=True`` there are no
    delimiter tokens and ``delimiters`` supplies the content instead.
    """
    if number_of_elements < 1:
        raise ValueError("Groups must have at least one element.")

    def wrap(_production: TokenProduction, output: list[Any], tag_handler: TagHandler | None) -> list[Any]:
        if empty:
            content = output[-number_of_elements:]
            output = output[:-number_of_elements]
            first = content[0]
            start_delim = Token("START_DELIMITER", delimiters[0], first.original, first.start, first.end)
            end_delim = Token("END_DELIMITER", delimiters[1], first.original, first.start, first.end)
        else:
            end_delim = output.pop()
            content = output[-number_of_elements:]
            output = output[:-number_of_elements]
            start_delim = output.pop()
        children = _as_nodes(content, tag_handler)
        token = Token(
            "GROUP", [start_delim.content, end_delim.content], children[0].original, start_delim.start, end_delim.end
        )
        output.append(ExprNode(token, children, traverse_step=traverse_group, tag_handler=tag_handler))
        return output

    return wrap


def operate(number_of_elements: int, empty: bool = False) -> Action:
    """Action applying an operation token to the last ``number_of_elements`` items.

    The body is ``operation ( args )`` (or ``operation args`` with
    ``empty=True``); the operation token becomes the node, the arguments its
    children.
    """
    # Zero is rejected too: output[-0:] would take the entire output stack.
    if number_of_elements < 1:
        raise ValueError("Operations must have at least one argument.")

    def wrap(_production: TokenProduction, output: list[Any], tag_handler: TagHandler | None) -> list[Any]:
        if empty:
            end_index = output[-1].end
            content = output[-number_of_elements:]
            output = output[:-number_of_elements]
        else:
            end_index = output.pop().end
            content = output[-number_of_elements:]
            output = output[:-number_of_elements]
            output.pop()  # start delimiter
        node = ExprNode(output.pop(), _as_nodes(content, tag_handler), tag_handler=tag_handler)
        node.end = end_index
        output.append(node)
        return output

    return wrap


def infix(_production: TokenProduction, output: list[Any], tag_handler: TagHandler | None) -> list[Any]:
    """Build an operator node from ``left operator right``."""
    right = output.pop()
    operator = output.pop()
    left = output.pop()
    output.append(ExprNode(operator, [left, right], traverse_step=traverse_infix, tag_handler=tag_handler))
    return output


def insert_infix(content: str, label: str) -> Action:
    """Action inserting an implicit ``label`` operator between the last two items."""

    def apply(production: TokenProduction, output: list[Any], tag_handler: TagHandler | None) -> list[Any]:
        operator_token = Token(label, content, output[-1].original, len(output[-1].original), -1)
        return infix(production, [*output[:-1], operator_token, output[-1]], tag_handler)

    return apply


def compose(*actions: Action) -> Action:
    """Action applying ``actions`` right to left (like function composition)."""

    def composed(production: TokenProduction, output: list[Any], tag_handler: TagHandler | None) -> list[Any]:
        for action in reversed(actions):
            output = action(production, output, tag_handler)
        return output

    return composed


def flatten(_production: TokenProduction, output: list[Any], _tag_handler: TagHandler | None) -> list[Any]:
    """Splice children equal to the last node (same label and content) into it."""
    node = output[-1]
    flattened: list[ExprNode] = []
    for child in node.children:
        if node.label == child.label and node.content == child.content:
            flattened += child.children
        else:
            flattened.append(child)
    node.children = flattened
    return output
