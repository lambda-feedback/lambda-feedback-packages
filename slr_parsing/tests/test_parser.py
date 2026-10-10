"""Native tests for the slr_parsing package.

compareExpressions has no dedicated slr_parsing test module (the engine is
exercised indirectly through the expression/quantity/criteria parsers), so
these are written fresh to cover the core building blocks.
"""

import pytest

from lambdafeedback.slr_parsing import (
    ExprNode,
    Lexeme,
    Token,
    build_expression_parser,
)


class TestToken:
    def test_str_and_repr(self):
        t = Token("NUM", "1", "1", 0, 0)
        assert str(t) == "NUM: 1"
        assert repr(t) == "NUM: 1"

    def test_equality_is_label_based(self):
        a = Token("NUM", "1", "1", 0, 0)
        b = Token("NUM", "2", "2", 0, 0)
        c = Token("OP", "+", "+", 0, 0)
        assert a == b  # same label
        assert a != c  # different label
        assert hash(a) == hash(b)


class TestExprNode:
    def test_content_string_of_leaf(self):
        node = ExprNode(Token("SYM", "x", "x", 0, 0), [])
        assert node.content_string() == "x"

    def test_children_wrapped_as_exprnodes(self):
        parent = ExprNode(
            Token("ADD", "+", "x+y", 1, 1),
            [Token("SYM", "x", "x+y", 0, 0), Token("SYM", "y", "x+y", 2, 2)],
        )
        assert len(parent.children) == 2
        assert all(isinstance(c, ExprNode) for c in parent.children)

    def test_copy_is_deep(self):
        node = ExprNode(Token("SYM", "x", "x", 0, 0), [])
        clone = node.copy()
        assert clone is not node
        assert clone.label == node.label
        assert clone.content_string() == node.content_string()

    def test_invalid_child_raises(self):
        with pytest.raises(TypeError):
            ExprNode(Token("ADD", "+", "+", 0, 0), ["not a token"])


class TestSLRExpressionParser:
    def _parser(self):
        # Numbers are caught as UNDEFINED lexemes; + and * are infix operators.
        return build_expression_parser(infix_operators=[("+", "ADD"), ("*", "MUL")])

    @pytest.mark.parametrize("expr", ["1+2", "1+2*3", "a*b+c"])
    def test_roundtrip_content_string(self, expr):
        parser = self._parser()
        tokens = parser.scan(expr)
        output = parser.parse(tokens)
        assert output[0].content_string() == expr

    def test_infix_builds_operator_root(self):
        parser = self._parser()
        output = parser.parse(parser.scan("1+2"))
        root = output[0]
        assert root.label == "ADD"
        assert len(root.children) == 2

    @pytest.mark.parametrize(
        ("operators", "root_label"),
        [
            ([("+", "ADD"), ("*", "MUL")], "ADD"),  # * listed later binds tighter: a+(b*c)
            ([("*", "MUL"), ("+", "ADD")], "MUL"),  # + listed later binds tighter: (a+b)*c
        ],
    )
    def test_later_operators_bind_tighter(self, operators, root_label):
        parser = build_expression_parser(infix_operators=operators)
        assert parser.parse(parser.scan("a+b*c"))[0].label == root_label

    def test_operators_are_left_associative(self):
        parser = build_expression_parser(infix_operators=[("-", "SUB"), ("^", "POW")])
        for text, label in (("a-b-c", "SUB"), ("a^b^c", "POW")):
            root = parser.parse(parser.scan(text))[0]
            assert root.label == label
            assert root.children[0].label == label
            assert root.children[1].label == "UNDEFINED"


class TestLexeme:
    @pytest.mark.parametrize(
        ("lexeme", "text", "length"),
        [
            (Lexeme(("+",)), "+x", 1),
            (Lexeme(("+",)), " +x", None),
            (Lexeme(("+",), space_before=True), "  +x", 3),
            (Lexeme(("+",), space_after=True), "+  x", 3),
            (Lexeme(("+",), True, True), "x", None),
            # The first form that matches wins, even when a later one is longer.
            (Lexeme((">", ">="), True, True), ">= x", 1),
            (Lexeme((">=", ">"), True, True), ">= x", 3),
            # A space in a form matches one or more spaces.
            (Lexeme(("written as",)), "written   as x", 12),
            (Lexeme(("written as",)), "writtenas", None),
            (Lexeme((" ",)), "   x", 3),
            (Lexeme((" ",)), "x", None),
            # A form starting with a space uses the spaces skipped before it.
            (Lexeme(("*", " "), True, True), "  x", 2),
            (Lexeme(("*", " "), True, True), " * x", 3),
        ],
    )
    def test_match_length(self, lexeme, text, length):
        assert lexeme.match(text) == length

    def test_token_content_includes_the_spaces(self):
        parser = build_expression_parser(infix_operators=[("+", "ADD")])
        assert [token.content for token in parser.scan("a  +  b")] == ["a", "  +  ", "b"]
