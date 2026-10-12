"""Tokens, expression-tree nodes and tree traversal steps."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any, TypeAlias

if TYPE_CHECKING:
    from .grammar import TagHandler

TraverseStep: TypeAlias = "Callable[[ExprNode, Callable[[ExprNode], Any]], list[tuple[bool, Any]]]"
"""Expands a node into ``(is_output, item)`` pairs: an action result to emit
(``True``) or a child node to traverse next (``False``)."""


def traverse_prefix(expr_node: ExprNode, action: Callable[[ExprNode], Any]) -> list[tuple[bool, Any]]:
    return [(True, action(expr_node)), *((False, child) for child in expr_node.children)]


def traverse_postfix(expr_node: ExprNode, action: Callable[[ExprNode], Any]) -> list[tuple[bool, Any]]:
    return [*((False, child) for child in expr_node.children), (True, action(expr_node))]


def traverse_infix(expr_node: ExprNode, action: Callable[[ExprNode], Any]) -> list[tuple[bool, Any]]:
    out: list[tuple[bool, Any]] = []
    for child in expr_node.children[:-1]:
        out += [(False, child), (True, action(expr_node))]
    return [*out, (False, expr_node.children[-1])]


def traverse_group(expr_node: ExprNode, action: Callable[[ExprNode], Any]) -> list[tuple[bool, Any]]:
    """Like prefix traversal, but emits ``action(node)[0]`` before and ``[1]`` after the children."""
    delimiters = action(expr_node)
    return [(True, delimiters[0]), *((False, child) for child in expr_node.children), (True, delimiters[1])]


class Token:
    """A scanned lexeme, or a grammar symbol.

    Tokens compare equal (and hash) by ``label`` only: the parser uses them as
    grammar symbols, where the content is irrelevant. This does not extend to
    :class:`ExprNode`, which compares by identity.
    """

    def __init__(self, label: str, content: Any, original: str, start: int, end: int) -> None:
        self.label = label
        self.content = content
        self.original = original
        self.start = start
        self.end = end

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ExprNode):
            return NotImplemented
        return isinstance(other, Token) and self.label == other.label

    def __hash__(self) -> int:
        return hash(self.label)

    def __str__(self) -> str:
        return f"{self.label}: {self.content}"

    # A short repr (rather than a constructor-style one) keeps debugger
    # watch windows and parser traces readable.
    __repr__ = __str__


class ExprNode(Token):
    """A node of the expression tree built by the parser.

    Unlike :class:`Token`, nodes compare equal (and hash) by identity: two
    distinct trees are never equal just because their roots share a label.
    """

    __eq__ = object.__eq__
    __hash__ = object.__hash__

    def __init__(
        self,
        token: Token,
        children: Iterable[Token],
        tag_handler: TagHandler | None = None,
        tags: Iterable[Any] | None = None,
        traverse_step: TraverseStep = traverse_prefix,
    ) -> None:
        super().__init__(token.label, token.content, token.original, token.start, token.end)
        self.children: list[ExprNode] = []
        for child in children:
            if isinstance(child, ExprNode):
                self.children.append(child)
            elif isinstance(child, Token):
                self.children.append(ExprNode(child, []))
            else:
                raise TypeError(f"Invalid child {child!s}")
        self.traverse_step = traverse_step
        """How :meth:`traverse` expands this node (see :data:`TraverseStep`)."""
        self.tags: set[Any] = tag_handler(self) if tag_handler is not None else set(tags or ())

    # copy() and tree_string() walk the tree with an explicit stack: input
    # nesting (e.g. thousands of brackets) must not hit the recursion limit.

    def _shallow_copy(self) -> ExprNode:
        token = Token(self.label, self.content, self.original, self.start, self.end)
        return ExprNode(token, [], tags=self.tags, traverse_step=self.traverse_step)

    def copy(self) -> ExprNode:
        """Deep copy of the tree; the copies' tag sets are not shared."""
        root = self._shallow_copy()
        stack = [(self, root)]
        while stack:
            node, clone = stack.pop()
            for child in node.children:
                child_clone = child._shallow_copy()
                clone.children.append(child_clone)
                stack.append((child, child_clone))
        return root

    def tree_string(self) -> str:
        lines: list[str] = []
        # (node, prefix of its first line, prefix of every later line)
        stack: list[tuple[ExprNode, str, str]] = [(self, "", "")]
        while stack:
            node, head, indent = stack.pop()
            lines.append(head + str(node).replace("\n", "\n" + indent))
            last = len(node.children) - 1
            for k in range(last, -1, -1):
                padding = "|   " if k < last else "    "
                stack.append((node.children[k], f"{indent}{k}: ", indent + padding))
        return "\n".join(lines)

    def content_string(self, max_depth: int | None = None) -> str:
        return "".join(self.traverse(lambda node: node.content, max_depth))

    def traverse(self, action: Callable[[ExprNode], Any], max_depth: int | None = None) -> list[Any]:
        """Apply ``action`` to nodes in the order given by each node's traverse step.

        Returns the emitted results; nodes deeper than ``max_depth`` are skipped.
        """
        stack = [(*item, 0) for item in reversed(self.traverse_step(self, action))]
        output = []
        while stack:
            is_output, elem, depth = stack.pop()
            if max_depth is None or depth <= max_depth:
                if is_output:
                    output.append(elem)
                else:
                    stack += [(*item, depth + 1) for item in reversed(elem.traverse_step(elem, action))]
        return output

    def original_string(self) -> str:
        """The slice of the original input spanned by this subtree."""
        start, end = self.start, self.end
        left = right = self.children
        while left:
            start = min(start, left[0].start)
            left = left[0].children
        while right:
            end = max(end, right[-1].end)
            right = right[-1].children
        return self.original[start : end + 1]

    def __str__(self) -> str:
        tags = str(self.tags) if self.tags else "{}"
        return f"{self.label}: {self.content} tags: {tags}"

    __repr__ = __str__
