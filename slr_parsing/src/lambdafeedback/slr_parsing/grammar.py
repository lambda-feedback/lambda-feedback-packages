"""Grammar building blocks: token specifications, productions and error handlers.

A grammar is a list of token specifications plus a list of productions.

Each token specification has a ``pattern`` (a literal string or a
:class:`Lexeme`), which is also how the symbol is written in production
strings, and a ``label``. There are four kinds:

:class:`TokenPattern`
    Input text matching the pattern becomes a ``label`` token. Grammar
    symbols that may also appear in input (``START``, ...) are declared this
    way too.
:class:`TokenMatcher`
    ``matcher(text) -> (matched, content)`` is tried at each position:
    ``matched`` is the consumed text (or ``None``) and ``content`` the
    token's content. For text that needs more than a :class:`Lexeme` (a run
    of digits, say).
:class:`CatchAll`
    At most one per grammar: runs of text that no other specification
    matches become ``label`` tokens (without it, such text is a
    :class:`ScanError`).
:class:`GrammarSymbol`
    A symbol that only appears in productions (a nonterminal) and is never
    scanned from input.

Productions are ``(head, body, action)`` triples (or :class:`Production`),
where ``head`` and ``body`` are scanned into grammar symbols and ``action``
builds the output tree when the production is reduced. When productions
conflict, the one listed later wins.

Productions headed by the start symbol are never reduced: reaching their end
accepts the input, so their action is never called (``None`` is fine).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
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


def _skip_spaces(text: str, index: int) -> int:
    """The index of the first character at or after ``index`` that isn't a space."""
    while text.startswith(" ", index):
        index += 1
    return index


class Lexeme(NamedTuple):
    """Any of ``forms`` (the first that matches), optionally with spaces around it.

    A space inside a form matches a run of one or more spaces (``"written
    as"`` matches ``"written   as"``). ``space_before`` and ``space_after``
    allow a run of spaces (possibly empty) on that side, which becomes part of
    the token's content.
    """

    forms: tuple[str, ...]
    space_before: bool = False
    space_after: bool = False

    def match(self, text: str, index: int = 0) -> int | None:
        """The length of the lexeme at ``index`` in ``text``, or ``None`` if it isn't there."""
        start = _skip_spaces(text, index) if self.space_before else index
        for form in self.forms:
            # A form starting with a space can use the spaces already skipped.
            if start > index and form.startswith(" "):
                end = _match_form(form.lstrip(" "), text, start)
            else:
                end = _match_form(form, text, start)
            if end is not None:
                return (_skip_spaces(text, end) if self.space_after else end) - index
        return None

    @property
    def weight(self) -> int:
        """Orders specifications for ties: the length of the longest form, plus 2 per side allowing spaces."""
        return max(map(len, self.forms)) + 2 * self.space_before + 2 * self.space_after


def _match_form(form: str, text: str, index: int) -> int | None:
    """Where ``form`` ends if it occurs in ``text`` at ``index`` (a space in it matching one or more spaces)."""
    for part_index, part in enumerate(form.split(" ")):
        if part_index > 0:
            if not text.startswith(" ", index):
                return None
            index = _skip_spaces(text, index)
        if not text.startswith(part, index):
            return None
        index += len(part)
    return index


def match_pattern(pattern: str | Lexeme, text: str, index: int = 0) -> int | None:
    """The length of ``pattern`` (a literal or :class:`Lexeme`) at ``index`` in ``text``, or ``None``."""
    if isinstance(pattern, Lexeme):
        return pattern.match(text, index)
    return len(pattern) if text.startswith(pattern, index) else None


def pattern_weight(pattern: str | Lexeme) -> int:
    """How a token specification's pattern ranks in ties between equally long matches (higher wins)."""
    return pattern.weight if isinstance(pattern, Lexeme) else len(pattern)


@dataclass(frozen=True)
class TokenPattern:
    """Input matching ``pattern`` becomes a ``label`` token (see the module docstring)."""

    pattern: str | Lexeme
    label: str


@dataclass(frozen=True)
class TokenMatcher:
    """``matcher`` reads ``label`` tokens from the input; ``pattern`` is the symbol in productions."""

    pattern: str | Lexeme
    label: str
    matcher: Matcher


@dataclass(frozen=True)
class CatchAll:
    """Runs of input no other specification matches become ``label`` tokens (at most one per grammar)."""

    pattern: str | Lexeme
    label: str


@dataclass(frozen=True)
class GrammarSymbol:
    """A symbol used only in productions (a nonterminal), never scanned from input."""

    pattern: str | Lexeme
    label: str


TokenSpec: TypeAlias = TokenPattern | TokenMatcher | CatchAll | GrammarSymbol
"""A token specification; see the module docstring for the four kinds."""

ErrorCondition: TypeAlias = Callable[[list[tuple[list[Token], list[Token]]], Token], bool]
"""``condition(items, next_symbol)``: whether an error action applies.

``items`` holds ``(before_dot, after_dot)`` symbol lists for the LR items of
the state where the error occurred.
"""


@dataclass
class ParseState:
    """Where a parse is: what error actions see, and may change to recover."""

    stack: list[int]
    """State numbers; the last is the current state."""
    lookahead: Token
    input_tokens: list[Token]
    """The tokens of the root being parsed."""
    remaining: deque[Token]
    """The tokens after ``lookahead``."""
    output: list[Any]
    """The output stack of tokens and :class:`~lambdafeedback.slr_parsing.ExprNode` s."""


ErrorAction: TypeAlias = "Callable[[SLRParser, ParseState], None]"
"""``action(parser, state)``: change ``state`` so that parsing can continue, or raise."""


class Production(NamedTuple):
    """A production ``head -> body``; ``action`` builds the output when it is reduced (see the module docstring)."""

    head: str
    body: str
    action: Action | None


class ErrorHandler(NamedTuple):
    """Used for the first empty parse-table entry whose ``condition`` holds."""

    condition: ErrorCondition
    action: ErrorAction
