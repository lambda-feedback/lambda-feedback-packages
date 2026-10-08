"""Behaviour of CriteriaGraph: building, feedback generation, trees and renderings."""

import json

import pytest

from lambdafeedback.criteria import (
    CriteriaGraph,
    CriteriaGraphError,
    CriterionNode,
    EvaluationNode,
    OutputNode,
)


def returns(*criteria):
    return lambda response: dict.fromkeys(criteria)


def equality_graph():
    """EQ -> EQ_TRUE -> SIMPLIFIED -> {SIMPLIFIED_TRUE, SIMPLIFIED_FALSE} -> END; EQ -> EQ_FALSE -> END."""
    graph = CriteriaGraph("eq")
    graph.add_node(CriteriaGraph.END)
    graph.add_evaluation_node("EQ", "response = answer", "compare", evaluate=returns("EQ_TRUE"))
    graph.attach("EQ", "EQ_TRUE", summary="equal", details="equal")
    graph.attach("EQ", "EQ_FALSE", summary="not equal", details="not equal")
    graph.attach("EQ_TRUE", "SIMPLIFIED", summary="simplified?", details="check", evaluate=returns("SIMPLIFIED_TRUE"))
    graph.attach("SIMPLIFIED", "SIMPLIFIED_TRUE", summary="yes", details="yes")
    graph.attach("SIMPLIFIED", "SIMPLIFIED_FALSE", summary="no", details="no")
    for criterion in ("EQ_FALSE", "SIMPLIFIED_TRUE", "SIMPLIFIED_FALSE"):
        graph.attach(criterion, "END")
    return graph


class TestBuilding:
    def test_attach_creates_nodes_of_the_kind_the_source_leads_to(self):
        graph = equality_graph()
        assert isinstance(graph.criteria["EQ_TRUE"], CriterionNode)
        assert isinstance(graph.evaluations["SIMPLIFIED"], EvaluationNode)
        assert isinstance(graph.outputs["END"], OutputNode)
        assert [edge.target.label for edge in graph.evaluations["EQ"].outgoing] == ["EQ_TRUE", "EQ_FALSE"]
        assert [edge.source.label for edge in graph.outputs["END"].incoming] == [
            "EQ_FALSE",
            "SIMPLIFIED_TRUE",
            "SIMPLIFIED_FALSE",
        ]

    def test_end_is_copied_into_each_graph(self):
        graph = equality_graph()
        assert graph.outputs["END"] is not CriteriaGraph.END
        assert CriteriaGraph.END.incoming == []

    @pytest.mark.parametrize(
        ("source", "target", "kwargs", "message"),
        [
            ("NOPE", "EQ_TRUE", {}, "Unknown node NOPE"),
            ("END", "EQ", {}, "END is an output node"),
            ("EQ", "SIMPLIFIED", {}, "Both EQ and SIMPLIFIED are evaluation nodes"),
            ("EQ_TRUE", "EQ_FALSE", {}, "Both EQ_TRUE and EQ_FALSE are criterion nodes"),
            ("EQ", "NEW", {"summary": "s"}, "summary and details must be specified"),
            ("EQ", "EQ_TRUE", {}, "EQ_TRUE is already attached to EQ"),
        ],
    )
    def test_invalid_attachments(self, source, target, kwargs, message):
        with pytest.raises(CriteriaGraphError, match=message):
            equality_graph().attach(source, target, **kwargs)

    def test_attach_rejects_keywords_for_the_other_node_kind(self):
        graph = equality_graph()
        with pytest.raises(CriteriaGraphError, match="cannot generate feedback"):
            graph.attach("EQ_TRUE", "NEW_E", summary="s", details="d", feedback_string_generator=lambda inputs: "x")
        with pytest.raises(CriteriaGraphError, match="cannot have sufficiencies"):
            graph.attach("EQ", "NEW_C", summary="s", details="d", sufficiencies=["X"])
        with pytest.raises(CriteriaGraphError, match="cannot have an evaluate function"):
            graph.attach("EQ", "NEW_C", summary="s", details="d", evaluate=lambda response: {})
        assert "NEW_E" not in graph.evaluations and "NEW_C" not in graph.criteria

    def test_add_sufficiencies_extends_without_duplicates(self):
        graph = equality_graph()
        graph.add_sufficiencies("SIMPLIFIED", ["EQ_TRUE"])
        graph.add_sufficiencies("SIMPLIFIED", ["EQ_TRUE", "EQ_FALSE"])
        assert graph.sufficiencies["SIMPLIFIED"] == ["EQ_TRUE", "EQ_FALSE"]
        with pytest.raises(CriteriaGraphError, match="Only evaluation nodes"):
            graph.add_sufficiencies("EQ_TRUE", ["EQ_FALSE"])


class TestFeedback:
    def test_starting_evaluations(self):
        graph = equality_graph()
        assert graph.starting_evaluations("SIMPLIFIED_TRUE") == ["SIMPLIFIED"]
        assert graph.starting_evaluations("EQ") == ["EQ"]
        with pytest.raises(CriteriaGraphError):
            graph.starting_evaluations("NOPE")

    def test_sufficiencies_move_the_start_to_the_sufficient_criteria(self):
        graph = equality_graph()
        graph.add_sufficiencies("SIMPLIFIED", ["EQ_TRUE"])
        assert graph.starting_evaluations("SIMPLIFIED_TRUE") == ["EQ"]

    def test_generate_feedback_follows_reached_criteria(self):
        feedback = equality_graph().generate_feedback("response", "EQ")
        assert list(feedback) == ["EQ_TRUE", "SIMPLIFIED_TRUE"]

    def test_evaluations_receive_the_response(self):
        seen = []
        graph = CriteriaGraph("g")
        graph.add_evaluation_node("E", "s", "d", evaluate=lambda response: seen.append(response) or {})
        graph.generate_feedback("x + 1", "E")
        assert seen == ["x + 1"]

    def test_replaced_evaluations_are_skipped(self):
        graph = equality_graph()
        graph.evaluations["SIMPLIFIED"].replacement = CriteriaGraph.END
        assert list(graph.generate_feedback("response", "EQ")) == ["EQ_TRUE"]

    def test_evaluation_without_evaluate_function(self):
        graph = CriteriaGraph("g")
        graph.add_evaluation_node("E", "s", "d")
        with pytest.raises(CriteriaGraphError, match="no evaluate function"):
            graph.generate_feedback("x", "E")


class TestTrees:
    def test_tree_structure_and_types(self):
        tree = equality_graph().build_tree("EQ", main_criteria=["SIMPLIFIED_TRUE"])
        data = tree.as_dict()
        assert (data["label"], data["type"]) == ("EQ", "evaluation")
        eq_true = next(child for child in tree.children if child.label == "EQ_TRUE")
        simplified_true = next(c for c in eq_true.children[0].children if c.label == "SIMPLIFIED_TRUE")
        assert simplified_true.type_label == "main_criterion"
        assert simplified_true.children[0].type_label == "output"
        assert simplified_true.parent.parent is eq_true
        assert json.loads(tree.to_json()) == data

    def test_revisited_nodes_become_return_leaves(self):
        graph = CriteriaGraph("loop")
        graph.add_evaluation_node("E", "s", "d")
        graph.attach("E", "C", summary="c", details="c")
        graph.attach("C", "E")
        tree = graph.build_tree("E")
        [criterion] = tree.children
        [leaf] = criterion.children
        assert leaf.label.startswith("RETURN")
        assert leaf.summary == "Go to: E"
        assert leaf.type_label == "output"

    def test_trees_start_from_each_starting_evaluation(self):
        trees = equality_graph().trees("SIMPLIFIED_TRUE")
        assert [tree.label for tree in trees] == ["SIMPLIFIED"]

    def test_tree_mermaid_highlights_special_nodes(self):
        mermaid = equality_graph().build_tree("EQ").to_mermaid(special_nodes=["EQ_FALSE"])
        assert mermaid.startswith("graph TD")
        assert 'EQ_0>"response = answer"]' in mermaid
        assert '[["not equal"]]' in mermaid


class TestGraphRenderings:
    def test_json(self):
        graph = equality_graph()
        graph.add_sufficiencies("SIMPLIFIED", ["EQ_TRUE"])
        data = json.loads(graph.to_json())
        assert data["evaluations"]["EQ"] == {
            "summary": "response = answer",
            "details": "compare",
            "incoming": [],
            "outgoing": ["EQ_TRUE", "EQ_FALSE"],
        }
        assert data["outputs"]["END"]["incoming"] == ["EQ_FALSE", "SIMPLIFIED_TRUE", "SIMPLIFIED_FALSE"]
        assert "outgoing" not in data["outputs"]["END"]
        assert data["sufficiencies"] == {"SIMPLIFIED": ["EQ_TRUE"]}

    def test_mermaid(self):
        graph = equality_graph()
        graph.add_sufficiencies("SIMPLIFIED", ["EQ_TRUE"])
        lines = graph.to_mermaid().split("\n\t")
        assert lines[0] == "flowchart TD"
        assert 'N_0_0(["EQ<br/>---<br/>compare"])' in lines
        assert "N_0_0 --> N_1_0" in lines
        assert "SIMPLIFIED -.-> EQ_TRUE" in lines
