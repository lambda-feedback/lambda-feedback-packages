"""The public reduction actions, tag helpers and traverse steps, each on a hand-built output stack."""

import pytest

from lambdafeedback.slr_parsing import (
    ExprNode,
    Token,
    add_tag,
    append,
    append_last,
    compose,
    flatten,
    group,
    infix,
    inherit_tags,
    insert_infix,
    intersection_rule,
    join,
    operate,
    remove_tag,
    replace_tag,
    traverse_group,
    traverse_postfix,
    union_rule,
)

ORIGINAL = "f(x) + y"


def token(label, content, start=0):
    return Token(label, content, ORIGINAL, start, start + len(content) - 1)


def node(label, content, start=0, children=(), tags=()):
    return ExprNode(token(label, content, start), list(children), tags=tags)


def production(head, *body):
    return token(head, head), [token(symbol, symbol) for symbol in body]


class TestStructuralActions:
    def test_append_makes_the_rest_of_the_body_children_of_its_first_item(self):
        first, second, third = node("L", "a"), node("X", "b"), node("X", "c")
        output = append(production("L", "L", "X", "X"), [node("S", "s"), first, second, third], None)
        assert [item.label for item in output] == ["S", "L"]
        assert output[-1].children == [second, third]

    def test_append_last_drops_the_separator(self):
        first, separator, last = node("L", "a"), node("SEP", ";"), node("X", "b")
        output = append_last(production("L", "L", ";", "X"), [first, separator, last], None)
        assert output == [first]
        assert first.children == [last]

    def test_join_merges_contents_into_the_first_item_relabelled(self):
        first, second = node("OTHER", "ab", 0), node("RESERVED", "cd", 2)
        output = join(production("OTHER", "OTHER", "RESERVED"), [first, second], None)
        assert output == [first]
        assert (first.label, first.content, first.end) == ("OTHER", "abcd", second.end)

    def test_flatten_splices_children_with_the_same_label_and_content(self):
        a, b, c = node("X", "a"), node("X", "b"), node("X", "c")
        inner = node("ADD", "+", children=[a, b])
        outer = node("ADD", "+", children=[inner, c])
        other = node("MUL", "*", children=[outer])
        assert flatten(production("E", "E"), [outer], None)[-1].children == [a, b, c]
        assert flatten(production("E", "E"), [other], None)[-1].children == [outer]

    def test_compose_applies_right_to_left(self):
        calls = []

        def record(name):
            def action(_production, output, _tag_handler):
                calls.append(name)
                return output

            return action

        compose(record("outer"), record("inner"))(production("E", "E"), [], None)
        assert calls == ["inner", "outer"]


class TestNodeBuildingActions:
    def test_operate_with_brackets(self):
        f, x, close = token("NAME", "f", 0), node("X", "x", 2), token("RPAR", ")", 3)
        output = operate(1)(production("E", "f", "(", "E", ")"), [f, token("LPAR", "(", 1), x, close], None)
        [call] = output
        assert (call.label, call.children, call.end) == ("NAME", [x], 3)

    def test_operate_without_brackets(self):
        f, x = token("NAME", "f", 0), node("X", "x", 2)
        [call] = operate(1, empty=True)(production("E", "f", "E"), [f, x], None)
        assert (call.children, call.end) == ([x], x.end)

    @pytest.mark.parametrize("make", [lambda: operate(0), lambda: group(0)])
    def test_zero_elements_are_rejected(self, make):
        with pytest.raises(ValueError, match="at least one"):
            make()

    def test_empty_group_uses_the_given_delimiters(self):
        a, b = node("X", "a", 0), node("X", "b", 1)
        [grouped] = group(2, empty=True, delimiters=("(", ")"))(production("E", "E", "E"), [a, b], None)
        assert grouped.children == [a, b]
        assert [delimiter.content for delimiter in grouped.delimiters] == ["(", ")"]
        assert (grouped.content, grouped.content_string()) == ("()", "(ab)")

    def test_insert_infix_adds_an_operator_that_spans_no_input(self):
        left, right = node("X", "f(x)", 0), node("X", "y", 7)
        [product] = insert_infix("*", "MUL")(production("E", "E", "E"), [left, right], None)
        assert (product.label, product.content, product.children) == ("MUL", "*", [left, right])
        assert product.original_string() == ORIGINAL

    def test_infix_runs_the_tag_handler(self):
        left, right = node("X", "a", tags={"t"}), node("X", "b", tags={"t", "u"})
        [operation] = infix(production("E", "E", "+", "E"), [left, token("ADD", "+"), right], inherit_tags)
        assert operation.tags == {"t", "u"}


class TestTags:
    def test_rules(self):
        assert union_rule({1}, {2}) == {1, 2}
        assert intersection_rule({1, 2}, {2, 3}) == {2}

    def test_inherit_tags_with_a_rule(self):
        parent = node("E", "+", children=[node("X", "a", tags={1, 2}), node("X", "b", tags={2, 3})])
        assert inherit_tags(parent) == {1, 2, 3}
        assert inherit_tags(parent, intersection_rule) == {2}
        assert inherit_tags(node("X", "a")) == set()

    def test_add_and_remove_respect_their_condition(self):
        tagged = node("X", "a", tags={"keep"})
        assert add_tag(tagged, "new", rule=lambda tags: "missing" in tags).tags == {"keep"}
        assert add_tag(tagged, "new").tags == {"keep", "new"}
        assert remove_tag(tagged, "new", rule=lambda tags: False).tags == {"keep", "new"}
        assert remove_tag(tagged, "new").tags == {"keep"}

    def test_replace_tag(self):
        tagged = node("X", "a", tags={"old"})
        assert replace_tag(tagged, "missing", "new").tags == {"old"}
        assert replace_tag(tagged, "old", "old").tags == {"old"}
        assert replace_tag(tagged, "old", "new").tags == {"new"}


class TestTraverseSteps:
    def test_postfix_emits_the_node_after_its_children(self):
        child = node("X", "a")
        parent = ExprNode(token("NEG", "-"), [child], traverse_step=traverse_postfix)
        assert parent.content_string() == "a-"

    def test_group_step_needs_a_group(self):
        with pytest.raises(TypeError, match="not a group"):
            traverse_group(node("X", "a"), lambda n: n.content)
