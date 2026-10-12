"""SLR(1) parser: table construction, scanning and parsing."""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Sequence
from typing import Any, Literal

from .errors import GrammarError, ParseError, ScanError
from .grammar import (
    Action,
    CatchAll,
    ErrorAction,
    ErrorCondition,
    ErrorHandler,
    GrammarSymbol,
    Lexeme,
    Matcher,
    ParseState,
    TagHandler,
    TokenMatcher,
    TokenPattern,
    TokenSpec,
    match_pattern,
    pattern_weight,
)
from .tags import inherit_tags
from .tokens import ExprNode, Token

logger = logging.getLogger(__name__)

# An LR(0) item: (production index, position of the dot in the body).
Item = tuple[int, int]
# A state is identified by its kernel items.
State = tuple[Item, ...]

# Parse-table entries: 0 <= e < len(states) shifts to state e; e == len(states)
# accepts; len(states) + p reduces by production p; -1 is a syntax error and
# -k (k >= 2) runs error handler k - 2.
_ERROR = -1


def _handler_entry(handler_index: int) -> int:
    return -2 - handler_index


def _handler_index(entry: int) -> int:
    return -2 - entry


class SLRParser:
    """An SLR(1) parser generated from token specifications and productions.

    See :mod:`lambdafeedback.slr_parsing.grammar` for how grammars are
    written. ``tag_handler`` computes the tags of nodes built by reduction
    actions; ``error_handlers`` recover from (or explain) syntax errors.
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
        # Heaviest patterns first: scan() keeps the longest match, so this
        # order only breaks ties between equal-length matches.
        self._check_token_specs(token_list)
        self.token_list: list[TokenSpec] = sorted(token_list, key=lambda spec: -pattern_weight(spec.pattern))
        self.productions = list(productions)
        self.start_symbol = start_symbol
        self.end_symbol = end_symbol
        self.null_symbol = null_symbol
        self._check_production_shapes()
        self.error_handlers = [self._error_handler(handler) for handler in error_handlers]
        self.tag_handler = tag_handler

        self._prepare_scanner()
        self.start_token = self._grammar_symbol(start_symbol, "Start symbol")
        self.end_token = self._grammar_symbol(end_symbol, "End symbol")
        self.null_token = self._grammar_symbol(null_symbol, "Null symbol")

        self._closures: dict[State, tuple[Item, ...]] = {}
        self._check_duplicate_productions()
        self._tokenise_productions()
        self._classify_symbols()
        self._compute_first()
        self._compute_follow()
        self._build_states()
        self._build_table()
        self._report_unreachable()

    # ------------------------------------------------------------------
    # Scanner
    # ------------------------------------------------------------------

    @staticmethod
    def _check_token_specs(token_list: Sequence[TokenSpec]) -> None:
        for spec in token_list:
            if not isinstance(spec, TokenPattern | TokenMatcher | CatchAll | GrammarSymbol):
                raise GrammarError(
                    f"Token specification {spec!r} is not a TokenPattern, TokenMatcher, CatchAll or GrammarSymbol."
                )
        if sum(isinstance(spec, CatchAll) for spec in token_list) > 1:
            raise GrammarError("Only one token type can be used to catch undefined lexemes.")

    def _prepare_scanner(self) -> None:
        self._catch_all = next((spec for spec in self.token_list if isinstance(spec, CatchAll)), None)
        self._expression_symbols = [
            (spec.pattern, spec.label) for spec in self.token_list if isinstance(spec, TokenPattern)
        ]
        self._expression_rules: list[tuple[str, Matcher]] = [
            (spec.label, spec.matcher) for spec in self.token_list if isinstance(spec, TokenMatcher)
        ]
        self._bnf_symbols: list[tuple[str | Lexeme, str]] = [(spec.pattern, spec.label) for spec in self.token_list]

    def scan(self, expr: str, mode: Literal["expression", "bnf"] = "expression") -> list[Token]:
        """Split ``expr`` into tokens, preferring the longest match at each position.

        Of equal-length matches, the specification with the longest pattern
        string wins; a matcher only wins over a pattern with a strictly
        longer match.

        ``mode="bnf"`` scans production strings into grammar symbols: every
        token specification is used as a plain pattern and no matchers run.
        Text that no specification matches is a :class:`GrammarError` in bnf
        mode (the catch-all only applies to expressions).
        """
        if mode == "expression":
            symbols, rules = self._expression_symbols, self._expression_rules
        elif mode == "bnf":
            symbols, rules = self._bnf_symbols, []
        else:
            raise ValueError(f"Unknown scan mode {mode!r}, expected 'expression' or 'bnf'.")

        tokens: list[Token] = []
        index = 0
        undefined = ""
        while index - len(undefined) < len(expr):
            label: str | None = None
            content: Any = ""
            length = 0
            for pattern, symbol_label in symbols:
                matched_length = match_pattern(pattern, expr, index)
                if matched_length is not None and matched_length > length:
                    length = matched_length
                    content = expr[index : index + length]
                    label = symbol_label
            rest = expr[index:] if rules else ""  # matchers read the text from where they are tried
            for rule_label, matcher in rules:
                matched, rule_content = matcher(rest)
                if matched is not None and len(matched) > length:
                    content = rule_content
                    length = len(matched)
                    label = rule_label

            token = None
            if label is None:
                undefined += expr[index]
                index += 1
            else:
                token = Token(label, content, expr, index, index + length - 1)
            if undefined and (token is not None or index >= len(expr)):
                if mode == "bnf":
                    raise GrammarError(f"Undeclared grammar symbol {undefined!r} in {expr!r}.")
                tokens.append(self._undefined_token(undefined, expr, index))
                undefined = ""
            if token is not None:
                tokens.append(token)
                index += length
        return tokens

    def _undefined_token(self, text: str, expr: str, index: int) -> Token:
        if self._catch_all is None:
            raise ScanError(f"Undefined input: {text}")
        return Token(self._catch_all.label, text, expr, index - len(text), index - 1)

    def _grammar_symbol(self, symbol: str, role: str) -> Token:
        try:
            tokens = self.scan(symbol, mode="bnf")
        except GrammarError:
            tokens = []
        if len(tokens) != 1:
            raise GrammarError(f"{role} {symbol!r} is not exactly one declared grammar symbol.")
        return tokens[0]

    # ------------------------------------------------------------------
    # Table construction
    # ------------------------------------------------------------------

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

    def _tokenise_productions(self) -> None:
        self._productions_token: list[tuple[Token, list[Token]]] = []
        for head, body, *_ in self.productions:
            body_tokens = self.scan(body, mode="bnf")
            if not body_tokens:
                raise GrammarError(f"Production {(head, body)} has an empty body; ε-productions are not supported.")
            self._productions_token.append((self._grammar_symbol(head, "Production head"), body_tokens))
        # Indexed like the productions: productions sharing a body keep their own actions.
        self._reductions: list[Action | None] = [production[2] for production in self.productions]
        # Production indices by head, in production order.
        self._productions_by_head: dict[Token, list[int]] = {}
        for p, (head_token, _) in enumerate(self._productions_token):
            self._productions_by_head.setdefault(head_token, []).append(p)

    def _classify_symbols(self) -> None:
        self._nonterminals: list[Token] = []
        for head, _ in self._productions_token:
            if head not in self._nonterminals:
                self._nonterminals.append(head)
        self._terminals: list[Token] = [self.end_token, self.null_token]
        for _, body in self._productions_token:
            for token in body:
                if token not in self._terminals and token not in self._nonterminals:
                    self._terminals.append(token)
        self._symbols = self._terminals + self._nonterminals
        self._symbol_ids = {symbol: j for j, symbol in enumerate(self._symbols)}

    def _compute_first(self) -> None:
        """FIRST sets of single symbols (ε-productions are not supported)."""
        # Dicts as ordered sets: membership is constant-time and the order stays deterministic.
        first: dict[Token, dict[Token, None]] = {t: {t: None} for t in self._terminals}
        first.update({nt: {} for nt in self._nonterminals})
        changed = True
        while changed:
            changed = False
            for nt in self._nonterminals:
                for p in self._productions_by_head[nt]:
                    for token in self._productions_token[p][1]:
                        for x in first[token]:
                            if x not in first[nt]:
                                first[nt][x] = None
                                changed = True
                        if self.null_token not in first[token]:
                            break
        self._first_dict = {symbol: list(symbols) for symbol, symbols in first.items()}

    def _first(self, tokens: Sequence[Token]) -> list[Token]:
        """FIRST set of a string of symbols."""
        if len(tokens) == 1:
            return self._first_dict[tokens[0]]
        result: list[Token] = []
        for token in tokens:
            for item in self._first_dict[token]:
                if item not in result and item != self.null_token:
                    result.append(item)
            if token != self.null_token:
                break
        return result

    def _compute_follow(self) -> None:
        follow: dict[Token, dict[Token, None]] = {nt: {} for nt in self._nonterminals}
        follow[self.start_token][self.end_token] = None
        changed = True
        while changed:
            changed = False
            for head, body in self._productions_token:
                for k, token in enumerate(body):
                    if token not in follow:
                        continue
                    rest = body[k + 1 :]
                    rest_first = self._first(rest) if rest else []
                    additions = rest_first
                    if not rest or self.null_token in rest_first:
                        additions = [*follow[head], *rest_first]
                    for item in additions:
                        if item != self.null_token and item not in follow[token]:
                            follow[token][item] = None
                            changed = True
        self._follow = {symbol: list(symbols) for symbol, symbols in follow.items()}

    def _closure(self, item_set: Sequence[Item]) -> tuple[Item, ...]:
        key = tuple(item_set)
        cached = self._closures.get(key)
        if cached is not None:
            return cached
        productions = self._productions_token
        closure = list(item_set)
        expanded: set[Token] = set()  # nonterminals whose productions are already in the closure
        for i, j in closure:  # the loop also visits the items it appends
            body = productions[i][1]
            if j < len(body) and body[j] in self._productions_by_head and body[j] not in expanded:
                expanded.add(body[j])
                closure += [(p, 0) for p in self._productions_by_head[body[j]]]
        self._closures[key] = result = tuple(closure)
        return result

    def _compute_transitions(self, item_set: Sequence[Item]) -> list[tuple[Token, list[Item]]]:
        transitions: dict[Token, list[Item]] = {}  # in order of first appearance
        for i, j in item_set:
            body = self._productions_token[i][1]
            if j < len(body):
                transitions.setdefault(body[j], []).append((i, j + 1))
        return list(transitions.items())

    def _build_states(self) -> None:
        start: State = tuple((p, 0) for p, (head, _) in enumerate(self._productions_token) if head == self.start_token)
        self.states: list[State] = [start]
        self._state_ids: dict[State, int] = {start: 0}
        self._transitions: dict[State, list[tuple[Token, list[Item]]]] = {}
        queue = deque([start])
        while queue:
            state = queue.popleft()
            transitions = self._compute_transitions(self._closure(state))
            self._transitions[state] = transitions
            for _, kernel in transitions:
                target = tuple(kernel)
                if target not in self._state_ids:
                    self._state_ids[target] = len(self.states)
                    self.states.append(target)
                    queue.append(target)

    def _build_table(self) -> None:
        candidates: list[list[list[tuple[int, int]]]] = [[[] for _ in self._symbols] for _ in self.states]
        for s, state in enumerate(self.states):
            targets = {symbol: self._state_ids[tuple(kernel)] for symbol, kernel in self._transitions[state]}
            for production_index, dot in self._closure(state):
                head, body = self._productions_token[production_index]
                if dot < len(body):  # shift / goto
                    symbol = body[dot]
                    candidates[s][self._symbol_ids[symbol]].append((production_index, targets[symbol]))
                elif head == self.start_token:  # accept
                    candidates[s][self._symbol_ids[self.end_token]].append((production_index, self._accept))
                else:  # reduce
                    for symbol in self._follow[head]:
                        reduction = (production_index, self._reduce_entry(production_index))
                        candidates[s][self._symbol_ids[symbol]].append(reduction)

        self.parsing_table: list[list[int]] = [
            [self._resolve(s, j, entries) for j, entries in enumerate(row)] for s, row in enumerate(candidates)
        ]

    def _resolve(self, s: int, j: int, entries: list[tuple[int, int]]) -> int:
        """Pick the table entry for state ``s`` and symbol ``j``.

        Conflicts go to the production listed last (ties to the first
        candidate); empty entries become errors, handled by the first error
        handler whose condition holds.
        """
        if not entries:
            items = [
                (self._productions_token[i][1][:dot], self._productions_token[i][1][dot:]) for i, dot in self.states[s]
            ]
            next_symbol = self._symbols[j]
            for k, handler in enumerate(self.error_handlers):
                if handler.condition(items, next_symbol):
                    return _handler_entry(k)
            return _ERROR
        best = entries[0]
        for entry in entries[1:]:
            if best[0] < entry[0]:
                best = entry
        return best[1]

    def _report_unreachable(self) -> None:
        targets = {entry for row in self.parsing_table for entry in row}
        states = [self.state_string(self.states[s]) for s in range(1, len(self.states)) if s not in targets]
        reductions = [
            f"{head} --> {body}"
            for p, (head, body, *_) in enumerate(self.productions)
            if self._productions_token[p][0] != self.start_token and self._reduce_entry(p) not in targets
        ]
        if states or reductions:
            logger.warning("Unreachable states: %s; unreachable reductions: %s", states, reductions)

    # Table entries (see _ERROR): shifts are state numbers, then accept, then one reduction per production.

    @property
    def _accept(self) -> int:
        return len(self.states)

    def _reduce_entry(self, production_index: int) -> int:
        return len(self.states) + production_index

    def _reduction_index(self, entry: int) -> int | None:
        """The production an entry reduces by (``None`` if it doesn't reduce)."""
        p = entry - len(self.states)
        return p if 0 <= p < len(self._productions_token) else None

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def parsing_action(self, state: int, symbol: Token) -> int:
        return self.parsing_table[state][self._symbol_ids[symbol]]

    def _next_action(self, state: ParseState) -> int:
        """The table entry for the current state and lookahead, after any error-recovery handlers, or raise."""
        action = self.parsing_action(state.stack[-1], state.lookahead)
        while action < 0:
            if action == _ERROR:
                raise self.parse_error(state)
            self.error_handlers[_handler_index(action)].action(self, state)
            action = self.parsing_action(state.stack[-1], state.lookahead)
        return action

    def _shift(self, target: int, state: ParseState, trace: bool) -> None:
        state.stack.append(target)
        state.output.append(ExprNode(state.lookahead, []))
        if trace:
            logger.debug("shift to %s  %s", self.state_string(self.states[target]), state.output)
        state.lookahead = state.remaining.popleft()

    def _reduce(self, p: int, state: ParseState, trace: bool) -> None:
        production = self._productions_token[p]
        reduction = self._reductions[p]
        if reduction is None:
            raise GrammarError(f"Production {tuple(self.productions[p][:2])} has no reduction action.")
        state.output = reduction(production, state.output, self.tag_handler)
        del state.stack[-len(production[1]) :]
        state.stack.append(self.parsing_action(state.stack[-1], production[0]))
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
        while action != self._accept:
            if action < self._accept:
                self._shift(action, state, trace)
            elif (p := self._reduction_index(action)) is not None:
                self._reduce(p, state, trace)
            else:
                raise ParseError(
                    f"Invalid parse table entry {action}.",
                    lookahead=state.lookahead,
                    remaining=list(state.remaining),
                    stack=state.stack,
                    output=state.output,
                )
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

    def _item_strings(self, state: State) -> list[str]:
        strings = []
        for production_index, dot in self._closure(state):
            body = self._productions_token[production_index][1]
            strings.append("".join(x.content for x in body[:dot]) + "." + "".join(x.content for x in body[dot:]))
        return strings

    def state_string(self, state: State) -> str:
        return f"I{self._state_ids[state]}: ({', '.join(self._item_strings(state))})"

    def parsing_table_to_string(self) -> str:
        lines = ["\t" + "\t".join(x.content for x in self._symbols)]
        for s, row in enumerate(self.parsing_table):
            lines.append(f"{s}\t" + "\t".join(self._entry_string(entry) for entry in row))
        return "\n".join(lines) + "\n"

    def _entry_string(self, entry: int) -> str:
        """``s<state>`` (shift), ``acc``, ``r<production>``, ``h<handler>`` (error handler) or ``-`` (error)."""
        if entry == _ERROR:
            return "-"
        if entry < 0:
            return f"h{_handler_index(entry)}"
        if entry < self._accept:
            return f"s{entry}"
        if entry == self._accept:
            return "acc"
        return f"r{self._reduction_index(entry)}"
