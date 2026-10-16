"""Engine tests on the textbook expression grammar.

E -> E + T | T        T -> T * F | F        F -> ( E ) | id
"""

import logging
from itertools import takewhile

import pytest

from lambdafeedback.slr_parsing import (
    Accept,
    CatchAll,
    ErrorHandler,
    GrammarError,
    ParseError,
    ScanError,
    SLRError,
    SLRParser,
    TokenMatcher,
    TokenPattern,
    create_node,
    group,
    infix,
    new_root_on_error,
    proceed,
)


def identifier(text):
    name = "".join(takewhile(lambda c: "a" <= c <= "z", text))
    return (name, name) if name else (None, None)


TOKENS = [
    TokenPattern("START", "START"),
    TokenPattern("END", "END"),
    TokenPattern("NULL", "NULL"),
    TokenPattern("E", "E"),
    TokenPattern("T", "T"),
    TokenPattern("F", "F"),
    TokenPattern("+", "PLUS"),
    TokenPattern("*", "TIMES"),
    TokenPattern("(", "LPAR"),
    TokenPattern(")", "RPAR"),
    TokenMatcher("id", "ID", identifier),
]

PRODUCTIONS = [
    ("START", "E", proceed),
    ("E", "E+T", infix),
    ("E", "T", proceed),
    ("T", "T*F", infix),
    ("T", "F", proceed),
    ("F", "(E)", group(1)),
    ("F", "id", create_node),
]


def make_parser(**kwargs):
    return SLRParser(TOKENS, PRODUCTIONS, "START", "END", "NULL", **kwargs)


def shape(node):
    """Compact tree shape, e.g. PLUS(a, TIMES(b, c))."""
    if not node.children:
        return node.content
    return f"{node.label}({', '.join(shape(child) for child in node.children)})"


def parse(text, parser=None):
    parser = parser or make_parser()
    return parser.parse(parser.scan(text))


class TestTableConstruction:
    def test_first_and_follow_sets(self):
        # These are the core of SLR(1).
        table = make_parser().table

        def labels(tokens):
            return {t.label for t in tokens}

        first = {nt.label: labels(table.first[nt]) for nt in table.nonterminals}
        follow = {nt.label: labels(table.follow[nt]) for nt in table.nonterminals}
        assert first == {"START": {"LPAR", "ID"}, "E": {"LPAR", "ID"}, "T": {"LPAR", "ID"}, "F": {"LPAR", "ID"}}
        assert follow == {
            "START": {"END"},
            "E": {"END", "PLUS", "RPAR"},
            "T": {"END", "PLUS", "RPAR", "TIMES"},
            "F": {"END", "PLUS", "RPAR", "TIMES"},
        }

    def test_canonical_state_count(self):
        # The canonical LR(0) collection for this grammar (plus START) has 12 states.
        assert len(make_parser().states) == 12

    def test_duplicate_productions_are_rejected(self):
        with pytest.raises(GrammarError, match="duplicate"):
            SLRParser(TOKENS, [*PRODUCTIONS, ("F", "id", proceed)], "START", "END", "NULL")

    def test_only_one_catch_all_token(self):
        tokens = [*TOKENS, CatchAll("U", "UNDEFINED"), CatchAll("V", "OTHER")]
        with pytest.raises(GrammarError, match="catch undefined"):
            SLRParser(tokens, PRODUCTIONS, "START", "END", "NULL")

    def test_production_without_action_fails_when_reduced(self):
        productions = [*PRODUCTIONS[:-1], ("F", "id", None)]
        parser = SLRParser(TOKENS, productions, "START", "END", "NULL")
        with pytest.raises(GrammarError, match="no reduction action"):
            parser.parse(parser.scan("a"))


class TestParsing:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("a", "a"),
            ("a+b*c", "PLUS(a, TIMES(b, c))"),
            ("a*b+c", "PLUS(TIMES(a, b), c)"),
            ("a+b+c", "PLUS(PLUS(a, b), c)"),
            ("(a+b)*c", "TIMES(GROUP(PLUS(a, b)), c)"),
        ],
    )
    def test_precedence_and_associativity(self, text, expected):
        [root] = parse(text)
        assert shape(root) == expected
        assert root.content_string() == text

    def test_original_string_of_subtree(self):
        [root] = parse("a+bb*c")
        assert root.children[1].original_string() == "bb*c"


class TestScanner:
    def test_longest_match_wins(self):
        tokens = [
            TokenPattern("START", "START"),
            TokenPattern("END", "END"),
            TokenPattern("NULL", "NULL"),
            TokenPattern("<", "LT"),
            TokenPattern("<=", "LE"),
        ]
        parser = SLRParser(tokens, [("START", "<=", proceed), ("START", "<", proceed)], "START", "END", "NULL")
        assert [t.label for t in parser.scan("<=<")] == ["LE", "LT"]

    def test_matcher_tokens_carry_their_content(self):
        assert [(t.label, t.content, t.start, t.end) for t in make_parser().scan("ab+c")] == [
            ("ID", "ab", 0, 1),
            ("PLUS", "+", 2, 2),
            ("ID", "c", 3, 3),
        ]

    def test_undefined_text_without_catch_all_is_a_scan_error(self):
        with pytest.raises(ScanError, match=r"Undefined input: \$"):
            make_parser().scan("a$b")

    def test_catch_all_token_collects_undefined_runs(self):
        parser = SLRParser([*TOKENS, CatchAll("U", "UNDEFINED")], PRODUCTIONS, "START", "END", "NULL")
        assert [(t.label, t.content) for t in parser.scan("a+$$")] == [("ID", "a"), ("PLUS", "+"), ("UNDEFINED", "$$")]


class TestErrors:
    @pytest.mark.parametrize(
        ("text", "message"),
        [
            ("a+", "Unexpected end of input."),
            ("", "Unexpected end of input."),
            ("a+*b", "Unexpected TIMES '*' at position 2."),
        ],
    )
    def test_parse_error_messages(self, text, message):
        with pytest.raises(ParseError) as info:
            parse(text)
        assert str(info.value) == message
        assert isinstance(info.value, SLRError)
        assert isinstance(info.value, ValueError)

    def test_parse_error_details(self):
        with pytest.raises(ParseError) as info:
            parse("a+*b")
        details = info.value.details()
        assert "remaining: [ID: b, END: END]" in details
        assert info.value.lookahead.label == "TIMES"

    def test_first_matching_error_handler_runs(self):
        class IncompleteError(Exception):
            pass

        def incomplete(*_args):
            raise IncompleteError

        handlers = [
            ErrorHandler(lambda items, next_symbol: next_symbol.label == "END", incomplete),
            ErrorHandler(lambda items, next_symbol: True, lambda *_args: pytest.fail("second handler ran")),
        ]
        with pytest.raises(IncompleteError):
            parse("a+", make_parser(error_handlers=handlers))

    def test_error_condition_receives_the_state_items(self):
        seen = []

        def condition(items, next_symbol):
            seen.append(("".join(t.content for t in items[0][0]), next_symbol.label))
            return False

        make_parser(error_handlers=[(condition, new_root_on_error)])  # action unused: condition is False
        assert ("E+", "END") in seen


def test_parse_tracing_is_logged(caplog):
    with caplog.at_level(logging.DEBUG, logger="lambdafeedback.slr_parsing.parser"):
        parse("a+b")
    messages = [record.getMessage() for record in caplog.records]
    assert any(m.startswith("shift to") for m in messages)
    assert any(m.startswith("reduce by E --> E+T") for m in messages)
    assert messages[-1] == "accept"


def test_parse_error_is_public_for_error_actions():
    def give_up(parser, state):
        raise parser.parse_error(state)

    with pytest.raises(ParseError, match="end of input"):
        parse("a+", make_parser(error_handlers=[(lambda items, next_symbol: True, give_up)]))


def test_parsing_table_string_tells_accept_from_reductions():
    # The accept entry was printed as "r0", like a reduction by production 0.
    parser = make_parser()
    rows = [line.split("\t")[1:] for line in parser.parsing_table_to_string().splitlines()[1:]]
    for table_row, printed_row in zip(parser.parsing_table, rows, strict=True):
        for entry, cell in zip(table_row, printed_row, strict=True):
            assert (cell == "acc") == isinstance(entry, Accept)


def test_walk_lists_each_node_before_its_children():
    root = parse("a+b*c")[0]
    walked = root.walk()
    assert walked[0] is root
    assert len(walked) == len({id(node) for node in walked})
    for node in walked:
        for child in node.children:
            assert walked.index(node) < walked.index(child)


def test_parsing_traces_at_debug_and_built_in_grammars_build_quietly(caplog):
    import logging

    with caplog.at_level(logging.DEBUG, logger="lambdafeedback.slr_parsing"):
        parse("a+b")
    assert "accept" in [record.getMessage() for record in caplog.records]
    assert all(record.levelno == logging.DEBUG for record in caplog.records)
