"""Generic expression-parser builder on top of :class:`SLRParser`."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from .actions import create_node, infix, relabel
from .grammar import Action, ErrorHandler, TokenSpec, catch_undefined
from .parser import SLRParser


def build_expression_parser(
    nodes: Sequence[TokenSpec] = (),
    infix_operators: Sequence[tuple[str, str]] = (),
    delimiters: Sequence[tuple[tuple[str, str], Action]] = (),
    undefined: tuple[str, str] | None = None,
    custom_tokens: Sequence[TokenSpec] = (),
    custom_productions: Sequence[tuple[str, str, Action | None]] = (),
    expression_node: tuple[str, str] | None = None,
    start: tuple[str, str] | None = None,
    null: tuple[str, str] | None = None,
    end: tuple[str, str] | None = None,
    error_handler: Sequence[ErrorHandler | tuple[Any, Any]] = (),
) -> SLRParser:
    """Build a parser for expressions made of operands, infix operators and delimiters.

    The grammar has one expression nonterminal (``expression_node``, default
    ``EXPRESSION_NODE``) with productions ``E -> label`` for each operand
    token spec in ``nodes`` (``(pattern, label)`` or ``(symbol, label,
    matcher)``) and ``E -> undefined`` for undefined text, ``E -> E op E`` for each ``(symbol, label)`` in
    ``infix_operators`` and ``E -> open E close`` for each
    ``((open, close), action)`` in ``delimiters``. ``custom_tokens`` and
    ``custom_productions`` extend the grammar; later productions win
    conflicts. All delimiter pairs share the ``START_DELIMITER`` and
    ``END_DELIMITER`` labels, so the grammar does not distinguish between
    pairs (the last pair's action is used, and mixed pairs such as ``(x]``
    are accepted).

    Later entries in ``infix_operators`` bind tighter: with
    ``[("+", "ADD"), ("*", "MUL")]``, ``a+b*c`` is ``a+(b*c)``; listed the
    other way round it would be ``(a+b)*c``. Every operator is
    left-associative (``a-b-c`` is ``(a-b)-c``), including ``^``: for a
    right-associative power, add a custom production. Spaces around operators and
    delimiters belong to their tokens' content, so ``content_string()``
    reproduces the input.

    ``undefined``, ``expression_node``, ``start``, ``null`` and ``end`` are
    ``(symbol, label)`` pairs overriding the default symbols; ``undefined``
    labels runs of text no other token matches (default ``UNDEFINED``).
    """
    labels_to_symbols: dict[str, list[str]] = {}
    for symbol, label in infix_operators:
        labels_to_symbols.setdefault(label, []).append(symbol)
    # One production per operator label, written with its first symbol.
    operator_symbols = [symbols[0] for symbols in labels_to_symbols.values()]
    operator_tokens = [
        (" *(" + "|".join(re.escape(s) for s in symbols) + ") *", label) for label, symbols in labels_to_symbols.items()
    ]

    undefined_spec = (*(undefined or ("UNDEFINED", "UNDEFINED")), catch_undefined)
    # A third element of None keeps the node symbol out of the scanner.
    expression_spec = (*(expression_node or ("EXPRESSION_NODE", "EXPRESSION_NODE")), None)
    start = start or ("START", "START")
    end = end or ("END", "END")
    null = null or ("NULL", "NULL")
    e = expression_spec[0]

    # Productions refer to nodes by label: a node's pattern (e.g. "[0-9]+") is
    # not a usable grammar symbol. Tokens compare by label, so a grammar-only
    # symbol spelled as the label matches every token the pattern scans.
    node_labels = list(dict.fromkeys(node[1] for node in nodes))
    node_symbols: list[TokenSpec] = [(re.escape(label), label, None) for label in node_labels]

    token_list: list[TokenSpec] = [undefined_spec, null, expression_spec, start, end, *nodes, *operator_tokens]
    token_list += node_symbols
    token_list += custom_tokens

    productions: list[tuple[str, str, Action | None]] = [(start[0], e, relabel)]
    productions += [(e, label, create_node) for label in node_labels]
    productions += [(e, undefined_spec[0], create_node)]
    productions += [(e, e + operator + e, infix) for operator in operator_symbols]
    for (open_delimiter, close_delimiter), _ in delimiters:
        token_list += [
            (re.escape(open_delimiter) + " *", "START_DELIMITER"),
            (" *" + re.escape(close_delimiter), "END_DELIMITER"),
        ]
    if delimiters:
        # Every pair scans to the same START_DELIMITER E END_DELIMITER body, so
        # one production covers them all; one per pair would leave all but the
        # last unreachable (and logged as such on every construction).
        (open_delimiter, close_delimiter), action = delimiters[-1]
        productions += [(e, open_delimiter + e + close_delimiter, action)]
    productions += custom_productions

    return SLRParser(token_list, productions, start[1], end[1], null[1], error_handler=error_handler)
