"""Exceptions raised by the parser engine, and error-recovery handlers.

All exceptions derive from :class:`SLRError` and from :class:`ValueError`, so
callers that treat bad input as a ``ValueError`` keep working.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .parser import SLRParser
    from .tokens import Token


class SLRError(Exception):
    """Base class for errors raised by the parser engine."""


class GrammarError(SLRError, ValueError):
    """The grammar (token list, productions or actions) is invalid."""


class ScanError(SLRError, ValueError):
    """The input contains text that no token matches."""


class ParseError(SLRError, ValueError):
    """The input does not match the grammar.

    The message is a short summary; :meth:`details` returns the full parser
    state (accepted and remaining tokens, stack and output) for debugging.
    """

    def __init__(
        self,
        message: str,
        *,
        lookahead: Token | None = None,
        accepted: list[Token] | None = None,
        remaining: list[Token] | None = None,
        stack: list[int] | None = None,
        output: list[Token] | None = None,
        state: str | None = None,
    ) -> None:
        super().__init__(message)
        self.lookahead = lookahead
        self.accepted = accepted or []
        self.remaining = remaining or []
        self.stack = stack or []
        self.output = output or []
        self.state = state

    def details(self) -> str:
        rule = "-" * 70
        lines = [
            rule,
            str(self),
            rule,
            f"accepted: {self.accepted}",
            f"current: {self.lookahead}",
            f"remaining: {self.remaining}",
            f"stack: {self.stack}",
            f"output: {self.output}",
        ]
        if self.state is not None:
            lines.append(f"state: {self.state}")
        lines.append(rule)
        return "\n".join(lines)


def new_root_on_error(
    parser: SLRParser, stack: list[int], a: Token, input_tokens: list[Token], tokens: list[Token], output: list[Any]
) -> tuple[list[int], Token, list[Token], list[Token], list[Any]]:
    """Error action: finish the current root here and parse the rest as new roots.

    The offending token is put back, so parsing resumes with it; ``parse``
    then returns one root per recovered segment. If no root can be finished
    here (nothing parsed yet, or the input already ended) the error is raised
    as a :class:`ParseError` instead.
    """
    if len(stack) == 1 or a == parser.end_token:
        raise parser.parse_error(stack, a, input_tokens, tokens, output)
    return stack, parser.end_token, input_tokens, [a, *tokens], output
