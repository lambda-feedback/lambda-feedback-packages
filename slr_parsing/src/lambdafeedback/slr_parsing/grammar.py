"""Grammar building blocks: token specifications, productions and error handlers.

A grammar is a list of token specifications plus a list of productions.

Token specifications are tuples in one of four shapes:

``(pattern, label)``
    A regular expression; input text matching it becomes a ``label`` token.
    Grammar symbols (``START``, nonterminals, ...) are declared this way too,
    since production strings are scanned with the same specifications.
``(pattern, label, matcher)``
    ``matcher(text) -> (matched, content)`` is tried at each position:
    ``matched`` is the consumed text (or ``None``) and ``content`` the
    token's content.
``(symbol, label, catch_undefined)``
    At most one per grammar: runs of text that no other specification
    matches become ``label`` tokens (without it, such text is a
    :class:`ScanError`).
``(symbol, label, None)``
    A symbol that only appears in productions and is never scanned from
    input.

Productions are ``(head, body, action)`` triples (or :class:`Production`),
where ``head`` and ``body`` are scanned into grammar symbols and ``action``
builds the output tree when the production is reduced. When productions
conflict, the one listed later wins.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, NamedTuple, TypeAlias

from .tokens import Token

if TYPE_CHECKING:
    from .parser import SLRParser
    from .tokens import ExprNode

TagHandler: TypeAlias = "Callable[[ExprNode], set[Any]]"
"""Computes a node's tags from the node (usually from its children)."""

TokenProduction: TypeAlias = tuple[Token, list[Token]]
"""A production after scanning: head symbol and body symbols."""

Action: TypeAlias = "Callable[[TokenProduction, list[Any], TagHandler | None], list[Any]]"
"""Reduction action: ``action(production, output, tag_handler) -> output``.

``output`` is the parser's output stack of :class:`Token`/``ExprNode`` items;
the action replaces the items for the production body with the new node(s).
"""

Matcher: TypeAlias = Callable[[str], tuple[str | None, Any]]
"""Custom scanner rule: ``matcher(text) -> (matched_text_or_None, content)``."""

TokenSpec: TypeAlias = tuple[str, str] | tuple[str, str, Any]
"""A token specification; see the module docstring for the accepted shapes."""

ErrorCondition: TypeAlias = Callable[[list[tuple[list[Token], list[Token]]], Token], bool]
"""``condition(items, next_symbol)``: whether an error action applies.

``items`` holds ``(before_dot, after_dot)`` symbol lists for the LR items of
the state where the error occurred.
"""

ErrorAction: TypeAlias = (
    "Callable[[SLRParser, list[int], Token, list[Token], list[Token], list[Any]],"
    " tuple[list[int], Token, list[Token], list[Token], list[Any]]]"
)
"""``action(parser, stack, lookahead, input_tokens, remaining, output)``.

Returns the (possibly modified) ``(stack, lookahead, input_tokens, remaining,
output)`` to continue parsing with, or raises.
"""


class Production(NamedTuple):
    head: str
    body: str
    action: Action | None


class ErrorHandler(NamedTuple):
    """Used for the first empty parse-table entry whose ``condition`` holds."""

    condition: ErrorCondition
    action: ErrorAction


def catch_undefined(label: str, content: str, original: str, start: int, end: int) -> Token:
    """Marker for the catch-all token specification (see module docstring)."""
    return Token(label, content, original, start, end)
