"""SLR(1) parser: table construction, scanning and parsing."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from typing import Any, Literal

from .errors import GrammarError, ParseError, ScanError
from .grammar import Action, ErrorHandler, Matcher, TagHandler, TokenSpec, catch_undefined
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


class SLRParser:
    """An SLR(1) parser generated from token specifications and productions.

    See :mod:`lambdafeedback.slr_parsing.grammar` for how grammars are
    written. ``tag_handler`` computes the tags of nodes built by reduction
    actions; ``error_handler`` entries recover from (or explain) syntax errors.
    """

    def __init__(
        self,
        token_list: Sequence[TokenSpec],
        productions: Sequence[tuple[str, str, Action | None]],
        start_symbol: str,
        end_symbol: str,
        null_symbol: str,
        error_handler: Sequence[ErrorHandler | tuple[Any, Any]] = (),
        tag_handler: TagHandler = inherit_tags,
    ) -> None:
        # Longest pattern strings first: scan() keeps the longest match, so this
        # order only breaks ties between equal-length matches.
        self.token_list: list[TokenSpec] = sorted(token_list, key=lambda spec: -len(spec[0]))
        self.productions = list(productions)
        self.start_symbol = start_symbol
        self.end_symbol = end_symbol
        self.null_symbol = null_symbol
        self._check_production_shapes()
        self.error_handler = [self._error_handler(handler) for handler in error_handler]
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

    def _prepare_scanner(self) -> None:
        catch_all = [spec for spec in self.token_list if len(spec) > 2 and spec[2] is catch_undefined]
        if len(catch_all) > 1:
            raise GrammarError("Only one token type can be used to catch undefined lexemes.")
        self._catch_undefined: TokenSpec | None = catch_all[0] if catch_all else None
        self._expression_symbols = [(re.compile(spec[0]), spec[1]) for spec in self.token_list if len(spec) == 2]
        self._expression_rules: list[tuple[str, Matcher]] = [
            (spec[1], spec[2])
            for spec in self.token_list
            if len(spec) > 2 and spec[2] is not None and spec[2] is not catch_undefined
        ]
        self._bnf_symbols = [(re.compile(spec[0]), spec[1]) for spec in self.token_list]

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
            rest = expr[index:]
            for pattern, symbol_label in symbols:
                match = pattern.match(rest)
                if match is not None and len(match.group()) > length:
                    content = match.group()
                    length = len(content)
                    label = symbol_label
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
        if self._catch_undefined is None:
            raise ScanError(f"Undefined input: {text}")
        return catch_undefined(self._catch_undefined[1], text, expr, index - len(text), index - 1)

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
    def _error_handler(handler: ErrorHandler | tuple[Any, Any]) -> ErrorHandler:
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
        first: dict[Token, list[Token]] = {t: [t] for t in self._terminals}
        first.update({nt: [] for nt in self._nonterminals})
        changed = True
        while changed:
            changed = False
            for nt in self._nonterminals:
                for head, body in self._productions_token:
                    if head != nt:
                        continue
                    for token in body:
                        for x in first[token]:
                            if x not in first[nt]:
                                first[nt].append(x)
                                changed = True
                        if self.null_token not in first[token]:
                            break
        self._first_dict = first

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
        follow: dict[Token, list[Token]] = {nt: [] for nt in self._nonterminals}
        follow[self.start_token].append(self.end_token)
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
                            follow[token].append(item)
                            changed = True
        self._follow = follow

    def _closure(self, item_set: Sequence[Item]) -> tuple[Item, ...]:
        key = tuple(item_set)
        cached = self._closures.get(key)
        if cached is not None:
            return cached
        productions = self._productions_token
        closure: list[Item] = []
        new_items = list(item_set)
        added = [False] * len(self._nonterminals)
        while new_items:
            closure += new_items
            new_items = []
            for i, j in closure:
                if j < len(productions[i][1]):
                    symbol = productions[i][1][j]
                    k = next((k for k, nt in enumerate(self._nonterminals) if nt == symbol), None)
                    if k is not None and not added[k]:
                        new_items += [(p, 0) for p, (head, _) in enumerate(productions) if head == symbol]
                        added[k] = True
        self._closures[key] = result = tuple(closure)
        return result

    def _compute_transitions(self, item_set: Sequence[Item]) -> list[tuple[Token, list[Item]]]:
        transitions: list[tuple[Token, list[Item]]] = []
        for i, j in item_set:
            body = self._productions_token[i][1]
            if j < len(body):
                symbol = body[j]
                for existing, targets in transitions:
                    if existing == symbol:
                        targets.append((i, j + 1))
                        break
                else:
                    transitions.append((symbol, [(i, j + 1)]))
        return transitions

    def _build_states(self) -> None:
        start: State = tuple((p, 0) for p, (head, _) in enumerate(self._productions_token) if head == self.start_token)
        self.states: list[State] = [start]
        self._state_ids: dict[State, int] = {start: 0}
        self._transitions: dict[State, list[tuple[Token, list[Item]]]] = {}
        queue = [start]
        while queue:
            state = queue.pop(0)
            transitions = self._compute_transitions(self._closure(state))
            self._transitions[state] = transitions
            for _, kernel in transitions:
                target = tuple(kernel)
                if target not in self._state_ids:
                    self._state_ids[target] = len(self.states)
                    self.states.append(target)
                    queue.append(target)

    def _build_table(self) -> None:
        n_states = len(self.states)
        candidates: list[list[list[tuple[int, int]]]] = [[[] for _ in self._symbols] for _ in self.states]
        for s, state in enumerate(self.states):
            for production_index, dot in self._closure(state):
                head, body = self._productions_token[production_index]
                if dot < len(body):  # shift / goto
                    symbol = body[dot]
                    for transition_symbol, kernel in self._transitions[state]:
                        if transition_symbol == symbol:
                            target = self._state_ids[tuple(kernel)]
                            candidates[s][self._symbol_ids[symbol]].append((production_index, target))
                            break
                elif head == self.start_token:  # accept
                    candidates[s][self._symbol_ids[self.end_token]].append((production_index, n_states))
                else:  # reduce
                    for symbol in self._follow[head]:
                        reduction = (production_index, n_states + production_index)
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
            for k, handler in enumerate(self.error_handler, 2):
                if handler.condition(items, next_symbol):
                    return -k
            return _ERROR
        best = entries[0]
        for entry in entries[1:]:
            if best[0] < entry[0]:
                best = entry
        return best[1]

    def _report_unreachable(self) -> None:
        n_states = len(self.states)
        targets = {entry for row in self.parsing_table for entry in row}
        states = [self.state_string(self.states[s]) for s in range(1, n_states) if s not in targets]
        reductions = [
            f"{head} --> {body}"
            for p, (head, body, *_) in enumerate(self.productions)
            if self._productions_token[p][0] != self.start_token and n_states + p not in targets
        ]
        if states or reductions:
            logger.warning("Unreachable states: %s; unreachable reductions: %s", states, reductions)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def parsing_action(self, state: int, symbol: Token) -> int:
        return self.parsing_table[state][self._symbol_ids[symbol]]

    def _run_error_handlers(
        self,
        action: int,
        stack: list[int],
        a: Token,
        input_tokens: list[Token],
        tokens: list[Token],
        output: list[Any],
    ) -> tuple[list[int], Token, list[Token], list[Token], list[Any], int]:
        """Apply error-recovery handlers until ``action`` is non-negative, or raise."""
        while action < 0:
            if action == _ERROR:
                raise self._parse_error(stack, a, input_tokens, tokens, output)
            handler = self.error_handler[-2 - action].action
            stack, a, input_tokens, tokens, output = handler(self, stack, a, input_tokens, tokens, output)
            action = self.parsing_action(stack[-1], a)
        return stack, a, input_tokens, tokens, output, action

    def _shift(
        self, action: int, a: Token, stack: list[int], tokens: list[Token], output: list[Any], trace: bool
    ) -> Token:
        stack.append(action)
        output.append(ExprNode(a, []))
        if trace:
            logger.debug("shift to %s  %s", self.state_string(self.states[action]), output)
        return tokens.pop(0)

    def _reduce(self, action: int, n_states: int, stack: list[int], output: list[Any], trace: bool) -> list[Any]:
        p = action - n_states
        production = self._productions_token[p]
        reduction = self._reductions[p]
        if reduction is None:
            raise GrammarError(f"Production {tuple(self.productions[p][:2])} has no reduction action.")
        output = reduction(production, output, self.tag_handler)
        del stack[-len(production[1]) :]
        stack.append(self.parsing_action(stack[-1], production[0]))
        if trace:
            body = "".join(x.content for x in production[1])
            logger.debug("reduce by %s --> %s  %s", production[0].content, body, output)
        return output

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
        tokens = [*input_tokens, self.end_token]
        n_states = len(self.states)
        trace = logger.isEnabledFor(logging.DEBUG)
        a = tokens.pop(0)
        stack = [0]
        output: list[Any] = []
        accepted = False
        while not accepted:
            action = self.parsing_action(stack[-1], a)
            stack, a, input_tokens, tokens, output, action = self._run_error_handlers(
                action, stack, a, input_tokens, tokens, output
            )
            if action < n_states:
                a = self._shift(action, a, stack, tokens, output, trace)
            elif action == n_states:
                logger.debug("accept")
                accepted = True
            elif action < n_states + len(self._productions_token):
                output = self._reduce(action, n_states, stack, output, trace)
            else:
                raise ParseError(
                    f"Invalid parse table entry {action}.", lookahead=a, remaining=tokens, stack=stack, output=output
                )
        return output, tokens

    def _parse_error(
        self, stack: list[int], a: Token, input_tokens: list[Token], tokens: list[Token], output: list[Any]
    ) -> ParseError:
        if a == self.end_token:
            message = "Unexpected end of input."
        else:
            message = f"Unexpected {a.label} {a.content!r} at position {a.start}."
        return ParseError(
            message,
            lookahead=a,
            accepted=input_tokens[: len(input_tokens) - len(tokens)],
            remaining=tokens,
            stack=stack,
            output=output,
            state=self.state_string(self.states[stack[-1]]),
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
        n_states = len(self.states)
        lines = ["\t" + "\t".join(x.content for x in self._symbols)]
        for s, row in enumerate(self.parsing_table):
            cells = []
            for entry in row:
                if entry < 0:
                    cells.append(f"e{-entry}")
                elif entry < n_states:
                    cells.append(f"s{entry}")
                else:
                    cells.append(f"r{entry - n_states}")
            lines.append(f"{s}\t" + "\t".join(cells))
        return "\n".join(lines) + "\n"
