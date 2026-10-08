"""Regression tests for bugs carried over from the v0.1 extraction."""

import logging

import pytest

from lambdafeedback.slr_parsing import (
    ExprNode,
    GrammarError,
    ParseError,
    SLRParser,
    Token,
    append,
    append_last,
    build_expression_parser,
    create_node,
    group,
    infix,
    inherit_tags,
    join,
    new_root_on_error,
    operate,
    proceed,
    relabel,
)


def leaf(label, content="x"):
    return ExprNode(Token(label, content, content, 0, 0), [])


class TestExprNodeTags:
    def test_nodes_without_tag_handler_do_not_share_tags(self):
        a, b = leaf("A"), leaf("B")
        a.tags.add("X")
        assert b.tags == set()

    def test_copy_does_not_share_tags(self):
        node = leaf("A")
        node.tags.add("X")
        clone = node.copy()
        clone.tags.add("Y")
        assert node.tags == {"X"}

    def test_inherited_tags_are_not_shared_with_the_child(self):
        child = leaf("A")
        child.tags.add("X")
        parent = ExprNode(Token("P", "p", "p", 0, 0), [child], tag_handler=inherit_tags)
        parent.tags.add("Y")
        assert child.tags == {"X"}

    def test_str_shows_a_single_tag(self):
        node = leaf("A")
        node.tags = {"X"}
        assert str(node) == "A: x tags: {'X'}"


class TestExpressionParserBuilder:
    def test_several_delimiter_pairs_build_without_unreachable_warnings(self, caplog):
        # One production per pair left all but the last unreachable (a WARNING per build).
        with caplog.at_level(logging.WARNING, logger="lambdafeedback.slr_parsing.parser"):
            parser = build_expression_parser(delimiters=[(("(", ")"), group(1)), (("[", "]"), group(1))])
        assert caplog.records == []
        assert [parser.parse(parser.scan(text))[0].label for text in ("(x)", "[x]")] == ["GROUP", "GROUP"]

    def test_custom_expression_node_symbol_is_not_a_literal_token(self):
        # The expression-node symbol ("E") must only exist in the grammar; an "E"
        # in the input is ordinary (undefined) text.
        parser = build_expression_parser(
            infix_operators=[("+", "ADD")],
            undefined=("O", "OTHER"),
            expression_node=("E", "EXPRESSION_NODE"),
        )
        tokens = parser.scan("2E+x")
        assert [(t.label, t.content) for t in tokens] == [("OTHER", "2E"), ("ADD", "+"), ("OTHER", "x")]
        assert parser.parse(tokens)[0].content_string() == "2E+x"

    def test_multi_character_infix_operator(self):
        parser = build_expression_parser(infix_operators=[("**", "POW"), ("+", "ADD")])
        root = parser.parse(parser.scan("a**b+c"))[0]
        assert root.content_string() == "a**b+c"

        def labels(node):
            return [node.label] + [label for child in node.children for label in labels(child)]

        assert sorted(labels(root)) == ["ADD", "POW", "UNDEFINED", "UNDEFINED", "UNDEFINED"]


class TestParserConstruction:
    def test_token_list_argument_is_not_mutated(self):
        token_list = [("START", "START"), ("END", "END"), ("NULL", "NULL"), ("E", "E"), (" *\\+ *", "+"), ("x", "x")]
        before = list(token_list)
        SLRParser(token_list, [("START", "E", None), ("E", "E+E", None), ("E", "x", None)], "START", "END", "NULL")
        assert token_list == before

    def test_scan_rejects_unknown_mode(self):
        parser = build_expression_parser(infix_operators=[("+", "ADD")])
        with pytest.raises(ValueError, match="mode"):
            parser.scan("1+2", mode="nonsense")

    def test_productions_with_the_same_body_keep_their_own_actions(self):
        # S -> A y | B z ; A -> x ; B -> x. Both "x" reductions share a body, and
        # each must run its own action (reductions used to be keyed by body).
        calls = []

        def record(name):
            def action(_production, output, _tag_handler):
                calls.append(name)
                return output

            return action

        symbols = ["START", "END", "NULL", "S", "A", "B", "x", "y", "z"]
        parser = SLRParser(
            [(s, s) for s in symbols],
            [
                ("START", "S", record("START")),
                ("S", "Ay", record("S->Ay")),
                ("S", "Bz", record("S->Bz")),
                ("A", "x", record("A->x")),
                ("B", "x", record("B->x")),
            ],
            "START",
            "END",
            "NULL",
        )
        parser.parse(parser.scan("xy"))
        assert calls == ["A->x", "S->Ay"]

    @pytest.mark.parametrize("action", [group, operate])
    def test_actions_reject_zero_elements(self, action):
        with pytest.raises(ValueError):
            action(0)


class TestGrammarValidation:
    SYMBOLS = (("START", "START"), ("END", "END"), ("NULL", "NULL"), ("E", "E"), ("x", "x"))

    def build(self, productions, start="START"):
        return SLRParser(self.SYMBOLS, productions, start, "END", "NULL")

    def test_empty_production_body_is_rejected(self):
        # Used to build, then crash with IndexError when parsing.
        with pytest.raises(GrammarError, match="empty body"):
            self.build([("START", "E", None), ("E", "", None), ("E", "x", None)])

    def test_production_head_must_be_one_symbol(self):
        # Used to silently use only the first symbol of "EE".
        with pytest.raises(GrammarError, match="Production head"):
            self.build([("START", "E", None), ("EE", "x", None)])

    def test_undeclared_symbol_in_a_body_is_rejected(self):
        # With a catch-all token, the typo "#Y" used to become an UNDEFINED symbol.
        with pytest.raises(GrammarError, match="#Y"):
            build_expression_parser(custom_productions=[("EXPRESSION_NODE", "EXPRESSION_NODE#Y", None)])

    def test_undeclared_start_symbol_is_a_grammar_error(self):
        # Used to raise ScanError.
        with pytest.raises(GrammarError, match="Start symbol"):
            self.build([("E", "x", None)], start="S")


class TestErrorRecovery:
    def new_root_parser(self):
        return build_expression_parser(
            infix_operators=[("+", "ADD")],
            delimiters=[(("(", ")"), group(1))],
            error_handler=[(lambda items, next_symbol: True, new_root_on_error)],
        )

    def test_new_root_on_error_starts_a_new_root_at_the_offending_token(self):
        parser = build_expression_parser(
            infix_operators=[("+", "ADD")],
            delimiters=[(("(", ")"), group(1))],
            error_handler=[(lambda items, next_symbol: next_symbol.label == "START_DELIMITER", new_root_on_error)],
        )
        output = parser.parse(parser.scan("(1+2)(3)"))
        assert [node.content_string() for node in output] == ["(1+2)", "(3)"]

    @pytest.mark.parametrize("text", ["", ")x", "x+", "x+)"])
    def test_new_root_on_error_raises_when_no_root_can_be_finished(self, text):
        # These used to loop forever.
        parser = self.new_root_parser()
        with pytest.raises(ParseError):
            parser.parse(parser.scan(text))

    def test_many_roots_do_not_exhaust_the_stack(self):
        # Each extra root used to add a level of recursion.
        parser = self.new_root_parser()
        output = parser.parse(parser.scan("(x)" * 2000))
        assert len(output) == 2000


class TestExprNodeEquality:
    def test_distinct_trees_with_the_same_root_label_are_not_equal(self):
        parser = build_expression_parser(infix_operators=[("+", "ADD")], delimiters=[(("(", ")"), group(1))])
        a = parser.parse(parser.scan("x+x"))[0]
        b = parser.parse(parser.scan("x+(x+x)"))[0]
        assert a != b
        assert a == a
        assert len({a, b}) == 2

    def test_tokens_never_equal_nodes(self):
        token = Token("A", "x", "x", 0, 0)
        node = ExprNode(token, [])
        assert token != node
        assert node != token
        assert token == Token("A", "y", "y", 0, 0)


class TestOneSymbolBodies:
    # A one-symbol body made output[:1 - 1] select nothing (IndexError).
    @pytest.mark.parametrize(("action", "label"), [(append, "X"), (append_last, "X"), (join, "E")])
    def test_action_on_one_symbol_body(self, action, label):
        symbols = [("START", "START"), ("END", "END"), ("NULL", "NULL"), ("E", "E"), ("x", "X")]
        parser = SLRParser(symbols, [("START", "E", proceed), ("E", "x", action)], "START", "END", "NULL")
        (root,) = parser.parse(parser.scan("x"))
        assert (root.label, root.content, root.children) == (label, "x", [])


class TestShapeValidation:
    SYMBOLS = (("START", "START"), ("END", "END"), ("NULL", "NULL"), ("E", "E"), ("x", "X"))

    @pytest.mark.parametrize(
        ("productions", "error_handler"),
        [
            pytest.param([("START", "E"), ("E", "x", create_node)], (), id="two-tuple production"),
            pytest.param([("START", "E", None), ("E", "x", "create_node")], (), id="non-callable action"),
            pytest.param([("START", "E", None), ("E", "x", create_node)], [(1, 2, 3)], id="three-tuple handler"),
            pytest.param(
                [("START", "E", None), ("E", "x", create_node)],
                [(True, new_root_on_error)],
                id="non-callable condition",
            ),
        ],
    )
    def test_malformed_grammar_entries_are_grammar_errors(self, productions, error_handler):
        # These used to raise IndexError/TypeError, the non-callable action only on the first parse.
        with pytest.raises(GrammarError):
            SLRParser(self.SYMBOLS, productions, "START", "END", "NULL", error_handler=error_handler)


class TestRelabel:
    def test_relabel_keeps_the_subtree(self):
        # relabel used to replace the node with a plain Token, dropping its children.
        symbols = [
            ("START", "START"),
            ("END", "END"),
            ("NULL", "NULL"),
            ("E", "E"),
            ("F", "F"),
            ("x", "X"),
            (r"\+", "P"),
        ]
        parser = SLRParser(
            symbols, [("START", "E", None), ("E", "F", relabel), ("F", "x+x", infix)], "START", "END", "NULL"
        )
        (root,) = parser.parse(parser.scan("x+x"))
        assert isinstance(root, ExprNode)
        assert (root.label, root.content_string()) == ("E", "x+x")


def test_public_type_aliases_are_exported():
    import lambdafeedback.slr_parsing as package

    for name in ("ErrorAction", "ErrorCondition", "TagCondition", "TagRule", "TraverseStep"):
        assert name in package.__all__
        assert hasattr(package, name)


class TestDeepNesting:
    DEPTH = 5000

    def deep_tree(self):
        parser = build_expression_parser(delimiters=[(("(", ")"), group(1))])
        return parser.parse(parser.scan("(" * self.DEPTH + "x" + ")" * self.DEPTH))[0]

    def test_copy_does_not_hit_the_recursion_limit(self):
        root = self.deep_tree()
        clone = root.copy()
        assert clone is not root
        assert clone.content_string() == root.content_string()
        clone.tags.add("T")
        assert root.tags == set()

    def test_tree_string_does_not_hit_the_recursion_limit(self):
        assert self.deep_tree().tree_string().count("\n") == self.DEPTH

    def test_tree_string_format(self):
        parser = build_expression_parser(infix_operators=[("+", "ADD")], delimiters=[(("(", ")"), group(1))])
        root = parser.parse(parser.scan("(a+b)+c"))[0]
        assert root.tree_string() == (
            "ADD: + tags: {}\n"
            "0: GROUP: ['(', ')'] tags: {}\n"
            "|   0: ADD: + tags: {}\n"
            "|       0: UNDEFINED: a tags: {}\n"
            "|       1: UNDEFINED: b tags: {}\n"
            "1: UNDEFINED: c tags: {}"
        )


class TestTraversal:
    def test_group_traversal_calls_the_action_once_per_node(self):
        # Actions may have side effects (units records a message per call).
        parser = build_expression_parser(delimiters=[(("(", ")"), group(1))])
        root = parser.parse(parser.scan("(x)"))[0]
        visited = []

        def action(node):
            visited.append(node.label)
            return node.content

        assert "".join(root.traverse(action)) == "(x)"
        assert visited == ["GROUP", "UNDEFINED"]
