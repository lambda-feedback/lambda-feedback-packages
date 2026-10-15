"""SLR(1) parse tables: LR(0) states, FIRST and FOLLOW sets, and the table's entries."""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeAlias, final

from .errors import GrammarError
from .grammar import ErrorHandler, TokenProduction
from .tokens import Token

Item: TypeAlias = tuple[int, int]
"""An LR(0) item: (production index, position of the dot in the body)."""
State: TypeAlias = tuple[Item, ...]
"""A state, identified by its kernel items."""


# ----------------------------------------------------------------------
# Table entries
# ----------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class Shift:
    """Shift the lookahead and go to ``state`` (for a nonterminal: the goto after a reduction)."""

    state: int

    def __str__(self) -> str:
        return f"s{self.state}"


@final
@dataclass(frozen=True, slots=True)
class Reduce:
    """Reduce by production ``production`` (its index in the grammar)."""

    production: int

    def __str__(self) -> str:
        return f"r{self.production}"


@final
@dataclass(frozen=True, slots=True)
class Accept:
    """Accept the input: a production of the start symbol is complete."""

    def __str__(self) -> str:
        return "acc"


@final
@dataclass(frozen=True, slots=True)
class Reject:
    """A syntax error that no error handler applies to."""

    def __str__(self) -> str:
        return "-"


@final
@dataclass(frozen=True, slots=True)
class Recover:
    """A syntax error, handled by error handler ``handler`` (its index in ``error_handlers``)."""

    handler: int

    def __str__(self) -> str:
        return f"h{self.handler}"


Entry: TypeAlias = Shift | Reduce | Accept | Reject | Recover
"""A parse-table entry; ``str()`` gives its form in :meth:`ParseTable.to_string`.

The entry classes are final: the parser tells them apart with ``type(entry) is ...``,
which is faster than ``isinstance`` or ``match`` in its innermost loop.
"""

ACCEPT = Accept()
REJECT = Reject()


# ----------------------------------------------------------------------
# The table
# ----------------------------------------------------------------------


class ParseTable:
    """The SLR(1) parse table of a grammar, built from its scanned productions.

    ``rows[state][symbol_id]`` is the :data:`Entry` for a state and a symbol
    (see :meth:`entry`). When productions conflict, the one listed last wins;
    empty entries go to the first error handler whose condition holds, or
    are :class:`Reject`. Productions headed by ``start`` accept rather than
    reduce. ε-productions are not supported.
    """

    def __init__(
        self,
        productions: Sequence[TokenProduction],
        start: Token,
        end: Token,
        null: Token,
        error_handlers: Sequence[ErrorHandler] = (),
    ) -> None:
        self.productions = list(productions)
        self.start_token = start
        self.end_token = end
        self.null_token = null
        self._error_handlers = list(error_handlers)
        self._closures: dict[State, tuple[Item, ...]] = {}
        # Production indices by head, in production order.
        self.productions_by_head: dict[Token, list[int]] = {}
        for p, (head, _) in enumerate(self.productions):
            self.productions_by_head.setdefault(head, []).append(p)

        self._classify_symbols()
        self._compute_first()
        self._compute_follow()
        self._build_states()
        self._build_rows()

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def entry(self, state: int, symbol: Token) -> Entry:
        """The entry for ``state`` with ``symbol`` next."""
        return self.rows[state][self.symbol_ids[symbol]]

    def goto(self, state: int, nonterminal: Token) -> int:
        """The state to go to from ``state`` after reducing to ``nonterminal``."""
        target = self.gotos[state].get(nonterminal)
        if target is None:
            raise GrammarError(f"No goto from state {state} on {nonterminal.label}.")
        return target

    # ------------------------------------------------------------------
    # Symbols, FIRST and FOLLOW
    # ------------------------------------------------------------------

    def _classify_symbols(self) -> None:
        self.nonterminals: list[Token] = []
        for head, _ in self.productions:
            if head not in self.nonterminals:
                self.nonterminals.append(head)
        self.terminals: list[Token] = [self.end_token, self.null_token]
        for _, body in self.productions:
            for token in body:
                if token not in self.terminals and token not in self.nonterminals:
                    self.terminals.append(token)
        self.symbols = self.terminals + self.nonterminals
        self.symbol_ids = {symbol: j for j, symbol in enumerate(self.symbols)}

    def _compute_first(self) -> None:
        """FIRST sets of single symbols (ε-productions are not supported)."""
        # Dicts as ordered sets: membership is constant-time and the order stays deterministic.
        first: dict[Token, dict[Token, None]] = {t: {t: None} for t in self.terminals}
        first.update({nt: {} for nt in self.nonterminals})
        changed = True
        while changed:
            changed = False
            for nt in self.nonterminals:
                for p in self.productions_by_head[nt]:
                    for token in self.productions[p][1]:
                        for x in first[token]:
                            if x not in first[nt]:
                                first[nt][x] = None
                                changed = True
                        if self.null_token not in first[token]:
                            break
        self.first: dict[Token, list[Token]] = {symbol: list(symbols) for symbol, symbols in first.items()}

    def first_of(self, tokens: Sequence[Token]) -> list[Token]:
        """FIRST set of a string of symbols."""
        if len(tokens) == 1:
            return self.first[tokens[0]]
        result: list[Token] = []
        for token in tokens:
            for item in self.first[token]:
                if item not in result and item != self.null_token:
                    result.append(item)
            if token != self.null_token:
                break
        return result

    def _compute_follow(self) -> None:
        follow: dict[Token, dict[Token, None]] = {nt: {} for nt in self.nonterminals}
        follow[self.start_token][self.end_token] = None
        changed = True
        while changed:
            changed = False
            for head, body in self.productions:
                for k, token in enumerate(body):
                    if token not in follow:
                        continue
                    rest = body[k + 1 :]
                    rest_first = self.first_of(rest) if rest else []
                    additions = rest_first
                    if not rest or self.null_token in rest_first:
                        additions = [*follow[head], *rest_first]
                    for item in additions:
                        if item != self.null_token and item not in follow[token]:
                            follow[token][item] = None
                            changed = True
        self.follow: dict[Token, list[Token]] = {symbol: list(symbols) for symbol, symbols in follow.items()}

    # ------------------------------------------------------------------
    # LR(0) states
    # ------------------------------------------------------------------

    def closure(self, item_set: Sequence[Item]) -> tuple[Item, ...]:
        """The LR(0) closure of ``item_set`` (cached)."""
        key = tuple(item_set)
        cached = self._closures.get(key)
        if cached is not None:
            return cached
        closure = list(item_set)
        expanded: set[Token] = set()  # nonterminals whose productions are already in the closure
        for i, j in closure:  # the loop also visits the items it appends
            body = self.productions[i][1]
            if j < len(body) and body[j] in self.productions_by_head and body[j] not in expanded:
                expanded.add(body[j])
                closure += [(p, 0) for p in self.productions_by_head[body[j]]]
        self._closures[key] = result = tuple(closure)
        return result

    def _compute_transitions(self, item_set: Sequence[Item]) -> list[tuple[Token, list[Item]]]:
        transitions: dict[Token, list[Item]] = {}  # in order of first appearance
        for i, j in item_set:
            body = self.productions[i][1]
            if j < len(body):
                transitions.setdefault(body[j], []).append((i, j + 1))
        return list(transitions.items())

    def _build_states(self) -> None:
        start: State = tuple((p, 0) for p, (head, _) in enumerate(self.productions) if head == self.start_token)
        self.states: list[State] = [start]
        self.state_ids: dict[State, int] = {start: 0}
        self._transitions: dict[State, list[tuple[Token, list[Item]]]] = {}
        queue = deque([start])
        while queue:
            state = queue.popleft()
            transitions = self._compute_transitions(self.closure(state))
            self._transitions[state] = transitions
            for _, kernel in transitions:
                target = tuple(kernel)
                if target not in self.state_ids:
                    self.state_ids[target] = len(self.states)
                    self.states.append(target)
                    queue.append(target)

    # ------------------------------------------------------------------
    # Entries
    # ------------------------------------------------------------------

    def _build_rows(self) -> None:
        # (production index, entry) candidates per state and symbol; _resolve picks one.
        candidates: list[list[list[tuple[int, Entry]]]] = [[[] for _ in self.symbols] for _ in self.states]
        for s, state in enumerate(self.states):
            targets = {symbol: self.state_ids[tuple(kernel)] for symbol, kernel in self._transitions[state]}
            for production_index, dot in self.closure(state):
                head, body = self.productions[production_index]
                if dot < len(body):  # shift / goto
                    symbol = body[dot]
                    candidates[s][self.symbol_ids[symbol]].append((production_index, Shift(targets[symbol])))
                elif head == self.start_token:  # accept
                    candidates[s][self.symbol_ids[self.end_token]].append((production_index, ACCEPT))
                else:  # reduce
                    for symbol in self.follow[head]:
                        candidates[s][self.symbol_ids[symbol]].append((production_index, Reduce(production_index)))

        self.rows: list[list[Entry]] = [
            [self._resolve(s, j, entries) for j, entries in enumerate(row)] for s, row in enumerate(candidates)
        ]
        self.gotos: list[dict[Token, int]] = [
            {nt: entry.state for nt in self.nonterminals if isinstance(entry := row[self.symbol_ids[nt]], Shift)}
            for row in self.rows
        ]
        """``gotos[state][nonterminal]``: the state after reducing to ``nonterminal`` (the :class:`Shift` entries)."""

    def _resolve(self, s: int, j: int, entries: list[tuple[int, Entry]]) -> Entry:
        """Pick the entry for state ``s`` and symbol ``j``.

        Conflicts go to the production listed last (ties to the first
        candidate); empty entries become errors, handled by the first error
        handler whose condition holds.
        """
        if not entries:
            items = [(self.productions[i][1][:dot], self.productions[i][1][dot:]) for i, dot in self.states[s]]
            next_symbol = self.symbols[j]
            for k, handler in enumerate(self._error_handlers):
                if handler.condition(items, next_symbol):
                    return Recover(k)
            return REJECT
        best = entries[0]
        for entry in entries[1:]:
            if best[0] < entry[0]:
                best = entry
        return best[1]

    def unreachable(self) -> tuple[list[str], list[str]]:
        """The states no entry leads to and the productions never reduced by (as strings), for diagnostics."""
        targets = {entry for row in self.rows for entry in row}
        states = [self.state_string(self.states[s]) for s in range(1, len(self.states)) if Shift(s) not in targets]
        reductions = [
            f"{head.content} --> {''.join(token.content for token in body)}"
            for p, (head, body) in enumerate(self.productions)
            if head != self.start_token and Reduce(p) not in targets
        ]
        return states, reductions

    # ------------------------------------------------------------------
    # Debugging aids
    # ------------------------------------------------------------------

    def _item_strings(self, state: State) -> list[str]:
        strings = []
        for production_index, dot in self.closure(state):
            body = self.productions[production_index][1]
            strings.append("".join(x.content for x in body[:dot]) + "." + "".join(x.content for x in body[dot:]))
        return strings

    def state_string(self, state: State) -> str:
        return f"I{self.state_ids[state]}: ({', '.join(self._item_strings(state))})"

    def to_string(self) -> str:
        """The table, tab-separated: ``s<state>`` (shift), ``acc``, ``r<production>``, ``h<handler>`` or ``-``."""
        lines = ["\t" + "\t".join(x.content for x in self.symbols)]
        for s, row in enumerate(self.rows):
            lines.append(f"{s}\t" + "\t".join(str(entry) for entry in row))
        return "\n".join(lines) + "\n"
