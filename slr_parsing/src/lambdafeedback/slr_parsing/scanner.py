"""Scanning: splitting text into tokens with a grammar's token specifications."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from .errors import GrammarError, ScanError
from .grammar import (
    CatchAll,
    GrammarSymbol,
    Lexeme,
    Matcher,
    TokenMatcher,
    TokenPattern,
    TokenSpec,
    match_pattern,
    pattern_weight,
)
from .tokens import Token


class Scanner:
    """Splits input text, and production strings, into tokens.

    Raises :class:`GrammarError` if a token specification is not a
    :class:`TokenPattern`, :class:`TokenMatcher`, :class:`CatchAll` or
    :class:`GrammarSymbol`, or if there is more than one :class:`CatchAll`.
    """

    def __init__(self, token_list: Sequence[TokenSpec]) -> None:
        _check_token_specs(token_list)
        # Heaviest patterns first: scan() keeps the longest match, so this
        # order only breaks ties between equal-length matches.
        self.token_list: list[TokenSpec] = sorted(token_list, key=lambda spec: -pattern_weight(spec.pattern))
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

    def grammar_symbol(self, symbol: str, role: str) -> Token:
        """The grammar symbol ``symbol`` names; ``role`` (e.g. ``"Start symbol"``) is for the error message.

        Raises :class:`GrammarError` unless ``symbol`` scans as exactly one declared symbol.
        """
        try:
            tokens = self.scan(symbol, mode="bnf")
        except GrammarError:
            tokens = []
        if len(tokens) != 1:
            raise GrammarError(f"{role} {symbol!r} is not exactly one declared grammar symbol.")
        return tokens[0]


def _check_token_specs(token_list: Sequence[TokenSpec]) -> None:
    for spec in token_list:
        if not isinstance(spec, TokenPattern | TokenMatcher | CatchAll | GrammarSymbol):
            raise GrammarError(
                f"Token specification {spec!r} is not a TokenPattern, TokenMatcher, CatchAll or GrammarSymbol."
            )
    if sum(isinstance(spec, CatchAll) for spec in token_list) > 1:
        raise GrammarError("Only one token type can be used to catch undefined lexemes.")
