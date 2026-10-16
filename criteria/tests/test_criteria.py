"""Native tests for the criteria package.

compareExpressions exercises the criteria parser/graph only through its core
evaluation tests, so these are written fresh to cover the DSL parser labels and
the CriteriaGraph structure directly.
"""

import json

import pytest

from lambdafeedback.criteria import (
    CriteriaGraph,
    CriteriaGraphError,
    build_criteria_parser,
    build_quantity_criteria_parser,
)
from lambdafeedback.slr_parsing import append_last, create_node, infix, join, proceed

RESERVED = {"learner": {"response": None}, "task": {"answer": None}}


def _parse(criterion):
    parser = build_criteria_parser(RESERVED)
    return parser.parse(parser.scan(criterion))[0]


class TestCriteriaParser:
    @pytest.mark.parametrize(
        "criterion, label",
        [
            ("response = answer", "EQUALITY"),
            ("response written as answer", "WRITTEN_AS"),
            ("response proportional to answer", "PROPORTIONAL_TO"),
            ("response contains answer", "CONTAINS"),
        ],
    )
    def test_operator_label(self, criterion, label):
        node = _parse(criterion)
        assert node.label == label

    @pytest.mark.parametrize(
        "criterion",
        ["response = answer", "response written as answer"],
    )
    def test_content_string_roundtrips(self, criterion):
        assert _parse(criterion).content_string() == criterion

    def test_where_clause_parses(self):
        node = _parse("response = answer where x = 1")
        assert node.label == "WHERE"


def _parse_quantity(criterion):
    parser = build_quantity_criteria_parser(RESERVED)
    return parser.parse(parser.scan(criterion))[0]


class TestQuantityCriteriaParser:
    @pytest.mark.parametrize("operator", ["matches", "=", "<=", ">=", "<", ">"])
    def test_relation_between_quantities(self, operator):
        node = _parse_quantity(f"response {operator} answer")
        assert node.label == f" {operator} "
        assert [(child.label, child.content_string()) for child in node.children] == [
            ("QUANTITY", "response"),
            ("QUANTITY", "answer"),
        ]

    def test_dimensions_match(self):
        node = _parse_quantity("dimension(response) matches dimension(answer)")
        assert node.label == " matches "
        assert [child.label for child in node.children] == [" dimension ", " dimension "]
        assert [child.children[0].content_string() for child in node.children] == ["response", "answer"]

    def test_other_text_is_a_quantity(self):
        node = _parse_quantity("response matches 9.81 m/s^2")
        assert [(child.label, child.content_string()) for child in node.children] == [
            ("QUANTITY", "response"),
            ("INPUT", "9.81 m/s^2"),
        ]


class TestCriteriaGraph:
    def test_build_and_serialise(self):
        g = CriteriaGraph("root")
        g.add_evaluation_node("EVAL", "eval", "eval details")
        g.add_criterion_node("CRIT", "crit", "crit details")
        g.add_output_node("OUT", "out", "out details")

        data = json.loads(g.to_json())
        assert "EVAL" in data["evaluations"]
        assert "CRIT" in data["criteria"]
        assert "OUT" in data["outputs"]

    def test_mermaid_returns_string(self):
        g = CriteriaGraph("root")
        g.add_evaluation_node("EVAL", "eval", "eval details")
        assert isinstance(g.to_mermaid(), str)

    def test_duplicate_evaluation_node_rejected(self):
        g = CriteriaGraph("root")
        g.add_evaluation_node("EVAL", "eval", "eval details")
        with pytest.raises(CriteriaGraphError):
            g.add_evaluation_node("EVAL", "eval", "eval details")


# The production table as it was written out by hand, before it was generated.
_HAND_WRITTEN_PRODUCTIONS = (
    ("START", "BOOL", create_node),
    ("BOOL", "EQUAL", proceed),
    ("BOOL", "ORDER", proceed),
    ("BOOL", "EQUAL where EQUAL", infix),
    ("BOOL", "EQUAL where EQUAL_LIST", infix),
    ("BOOL", "RESERVED written as OTHER", infix),
    ("BOOL", "RESERVED written as RESERVED", infix),
    ("EQUAL", "OTHER proportional to OTHER", infix),
    ("EQUAL", "RESERVED proportional to OTHER", infix),
    ("EQUAL", "OTHER proportional to RESERVED", infix),
    ("EQUAL", "RESERVED proportional to RESERVED", infix),
    ("BOOL", "RESERVED contains OTHER", infix),
    ("BOOL", "RESERVED contains RESERVED", infix),
    ("EQUAL_LIST", "EQUAL;EQUAL", infix),
    ("EQUAL_LIST", "EQUAL_LIST;EQUAL", append_last),
    ("EQUAL", "OTHER = OTHER", infix),
    ("EQUAL", "RESERVED = OTHER", infix),
    ("EQUAL", "OTHER = RESERVED", infix),
    ("EQUAL", "RESERVED = RESERVED", infix),
    ("EQUAL", "OTHER ORDER OTHER", infix),
    ("EQUAL", "RESERVED ORDER OTHER", infix),
    ("EQUAL", "OTHER ORDER RESERVED", infix),
    ("EQUAL", "RESERVED ORDER RESERVED", infix),
    ("OTHER", "RESERVED OTHER", join),
    ("OTHER", "OTHER RESERVED", join),
    ("OTHER", "OTHER OTHER", join),
)


def test_generated_productions_match_the_hand_written_table():
    from lambdafeedback.criteria.grammar import PRODUCTIONS

    assert PRODUCTIONS == _HAND_WRITTEN_PRODUCTIONS
