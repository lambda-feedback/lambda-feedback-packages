"""SLR(1) parser: a scanner and a parse table, and the parse that drives them."""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Sequence
from typing import Any, Literal

from .errors import GrammarError, ParseError
from .grammar import Action, ErrorAction, ErrorCondition, ErrorHandler, ParseState, TagHandler, TokenSpec
from .scanner import Scanner
from .table import Accept, Entry, ParseTable, Recover, Reduce, Reject, Shift, State
from .tags import inherit_tags
from .tokens import ExprNode, Token

logger = logging.getLogger(__name__)


class SLRParser:
    """An SLR(1) parser generated from token specifications and productions.

    See :mod:`lambdafeedback.slr_parsing.grammar` for how grammars are
    written. ``tag_handler`` computes the tags of nodes built by reduction
    actions; ``error_handlers`` recover from (or explain) syntax errors.

    The work is split between a :class:`~lambdafeedback.slr_parsing.scanner.Scanner`
    (``scanner``), which turns text into tokens, and a
    :class:`~lambdafeedback.slr_parsing.table.ParseTable` (``table``), built
    from the productions; the parser runs the parse with them.
    """

    def __init__(
        self,
        token_list: Sequence[TokenSpec],
        productions: Sequence[tuple[str, str, Action | None]],
        start_symbol: str,
        end_symbol: str,
        null_symbol: str,
        error_handlers: Sequence[ErrorHandler | tuple[ErrorCondition, ErrorAction]] = (),
        tag_handler: TagHandler = inherit_tags,
    ) -> None:
        self.scanner = Scanner(token_list)
        self.token_list = self.scanner.token_list
        self.productions = list(productions)
        self.start_symbol = start_symbol
        self.end_symbol = end_symbol
        self.null_symbol = null_symbol
        self._check_production_shapes()
        self.error_handlers = [self._error_handler(handler) for handler in error_handlers]
        self.tag_handler = tag_handler

        self.start_token = self.scanner.grammar_symbol(start_symbol, "Start symbol")
        self.end_token = self.scanner.grammar_symbol(end_symbol, "End symbol")
        self.null_token = self.scanner.grammar_symbol(null_symbol, "Null symbol")

        self._check_duplicate_productions()
        # Indexed like the productions: productions sharing a body keep their own actions.
        self._reductions: list[Action | None] = [production[2] for production in self.productions]
        self.table = ParseTable(
            self._tokenise_productions(), self.start_token, self.end_token, self.null_token, self.error_handlers
        )
        self.states = self.table.states
        self.parsing_table = self.table.rows
        # Looked up on every parse step, so bound here rather than reached through the table's methods.
        self._symbol_ids = self.table.symbol_ids
        self._gotos = self.table.gotos
        self._report_unreachable()

    # ------------------------------------------------------------------
    # Grammar
    # ------------------------------------------------------------------

    def scan(self, expr: str, mode: Literal["expression", "bnf"] = "expression") -> list[Token]:
        """Split ``expr`` into tokens (see :meth:`~lambdafeedback.slr_parsing.scanner.Scanner.scan`)."""
        return self.scanner.scan(expr, mode)

    def _check_production_shapes(self) -> None:
        for production in self.productions:
            if not (
                isinstance(production, tuple | list)
                and len(production) == 3
                and isinstance(production[0], str)
                and isinstance(production[1], str)
                and (production[2] is None or callable(production[2]))
            ):
                raise GrammarError(f"Production {production!r} is not a (head, body, action-or-None) triple.")

    @staticmethod
    def _error_handler(handler: ErrorHandler | tuple[ErrorCondition, ErrorAction]) -> ErrorHandler:
        if not (isinstance(handler, tuple | list) and len(handler) == 2 and all(callable(part) for part in handler)):
            raise GrammarError(f"Error handler {handler!r} is not a (condition, action) pair of callables.")
        return ErrorHandler(*handler)

    def _check_duplicate_productions(self) -> None:
        seen: set[tuple[str, str]] = set()
        duplicates = []
        for head, body, *_ in self.productions:
            if (head, body) in seen:
                duplicates.append(f"duplicate: {(head, body)}")
            seen.add((head, body))
        if duplicates:
            raise GrammarError("There are duplicate productions:\n" + "\n".join(duplicates))

    def _tokenise_productions(self) -> list[tuple[Token, list[Token]]]:
        productions = []
        for head, body, *_ in self.productions:
            body_tokens = self.scanner.scan(body, mode="bnf")
            if not body_tokens:
                raise GrammarError(f"Production {(head, body)} has an empty body; ε-productions are not supported.")
            productions.append((self.scanner.grammar_symbol(head, "Production head"), body_tokens))
        return productions

    def _report_unreachable(self) -> None:
        states, reductions = self.table.unreachable()
        if states or reductions:
            logger.warning("Unreachable states: %s; unreachable reductions: %s", states, reductions)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def parsing_action(self, state: int, symbol: Token) -> Entry:
        """The parse-table entry for ``state`` with ``symbol`` next."""
        return self.parsing_table[state][self._symbol_ids[symbol]]

    def _next_action(self, state: ParseState) -> Shift | Reduce | Accept:
        """The table entry for the current state and lookahead, after any error-recovery handlers, or raise."""
        action = self.parsing_action(state.stack[-1], state.lookahead)
        while type(action) is Recover:
            self.error_handlers[action.handler].action(self, state)
            action = self.parsing_action(state.stack[-1], state.lookahead)
        if type(action) is Reject:
            raise self.parse_error(state)
        return action

    def _shift(self, target: int, state: ParseState, trace: bool) -> None:
        state.stack.append(target)
        state.output.append(ExprNode(state.lookahead, []))
        if trace:
            logger.debug("shift to %s  %s", self.state_string(self.states[target]), state.output)
        state.lookahead = state.remaining.popleft()

    def _reduce(self, p: int, state: ParseState, trace: bool) -> None:
        production = self.table.productions[p]
        reduction = self._reductions[p]
        if reduction is None:
            raise GrammarError(f"Production {tuple(self.productions[p][:2])} has no reduction action.")
        state.output = reduction(production, state.output, self.tag_handler)
        del state.stack[-len(production[1]) :]
        state.stack.append(self._gotos[state.stack[-1]][production[0]])
        if trace:
            body = "".join(x.content for x in production[1])
            logger.debug("reduce by %s --> %s  %s", production[0].content, body, state.output)

    def parse(self, input_tokens: Sequence[Token]) -> list[Any]:
        """Parse scanned tokens; returns the output roots (normally exactly one).

        Raises :class:`ParseError` on a syntax error that no error handler
        recovers from. Set the ``lambdafeedback.slr_parsing.parser``
        logger to DEBUG to trace shifts and reductions.
        """
        roots, remaining = self._parse_root(list(input_tokens))
        # An error handler (such as new_root_on_error) can accept before the
        # end of the input; the tokens left over are parsed as further roots.
        while remaining and remaining != [self.end_token]:
            more, remaining = self._parse_root(remaining)
            roots += more
        return roots

    def _parse_root(self, input_tokens: list[Token]) -> tuple[list[Any], list[Token]]:
        """Parse from the start state until accept; returns the output and the tokens left after it."""
        if input_tokens and input_tokens[-1] == self.end_token:
            input_tokens = input_tokens[:-1]
        remaining = deque([*input_tokens, self.end_token])
        state = ParseState(
            stack=[0], lookahead=remaining.popleft(), input_tokens=input_tokens, remaining=remaining, output=[]
        )
        trace = logger.isEnabledFor(logging.DEBUG)
        action = self._next_action(state)
        # type() checks rather than match or isinstance: this is the parser's innermost loop.
        while type(action) is not Accept:
            if type(action) is Shift:
                self._shift(action.state, state, trace)
            elif type(action) is Reduce:
                self._reduce(action.production, state, trace)
            action = self._next_action(state)
        logger.debug("accept")
        return state.output, list(state.remaining)

    def parse_error(self, state: ParseState) -> ParseError:
        """The :class:`ParseError` for a syntax error at ``state.lookahead`` (for error actions that give up)."""
        lookahead = state.lookahead
        if lookahead == self.end_token:
            message = "Unexpected end of input."
        else:
            message = f"Unexpected {lookahead.label} {lookahead.content!r} at position {lookahead.start}."
        return ParseError(
            message,
            lookahead=lookahead,
            accepted=state.input_tokens[: len(state.input_tokens) - len(state.remaining)],
            remaining=list(state.remaining),
            stack=state.stack,
            output=state.output,
            state=self.state_string(self.states[state.stack[-1]]),
        )

    # ------------------------------------------------------------------
    # Debugging aids
    # ------------------------------------------------------------------

    def state_string(self, state: State) -> str:
        return self.table.state_string(state)

    def parsing_table_to_string(self) -> str:
        """The parse table, tab-separated (see :meth:`~lambdafeedback.slr_parsing.table.ParseTable.to_string`)."""
        return self.table.to_string()
