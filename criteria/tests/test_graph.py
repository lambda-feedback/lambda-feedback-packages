"""Behaviour of CriteriaGraph: building, feedback generation, trees and renderings."""

import json

import pytest

from lambdafeedback.criteria import (
    CriteriaGraph,
    CriteriaGraphError,
    CriterionNode,
    EvaluationNode,
    Node,
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
            ("EQ", "END", {}, "END is an output node. Only criterion nodes"),
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

    def test_attach_to_existing_target_rejects_node_options(self):
        graph = equality_graph()
        with pytest.raises(CriteriaGraphError, match="SIMPLIFIED already exists"):
            graph.attach("EQ_FALSE", "SIMPLIFIED", summary="s", details="d")
        with pytest.raises(CriteriaGraphError, match="SIMPLIFIED already exists"):
            graph.attach("EQ_FALSE", "SIMPLIFIED", evaluate=returns("X"))
        assert [edge.target.label for edge in graph.criteria["EQ_FALSE"].outgoing] == ["END"]

    def test_add_node_rejects_other_types(self):
        with pytest.raises(CriteriaGraphError, match="Can only add"):
            CriteriaGraph("g").add_node(Node("X", "s", "d"))

    def test_labels_are_unique_across_node_kinds(self):
        graph = equality_graph()
        graph.add_sufficiencies("SIMPLIFIED", ["EQ_TRUE"])
        with pytest.raises(CriteriaGraphError, match="Evaluation node SIMPLIFIED is already defined"):
            graph.add_criterion_node("SIMPLIFIED", "s", "d")
        with pytest.raises(CriteriaGraphError, match="Criterion node EQ_TRUE is already defined"):
            graph.add_output_node("EQ_TRUE", "s", "d")
        assert graph.sufficiencies["SIMPLIFIED"] == ["EQ_TRUE"]

    def test_add_node_keeps_replacement(self):
        node = EvaluationNode("X", "s", "d")
        node.replacement = CriteriaGraph.END
        graph = CriteriaGraph("g")
        graph.add_node(node)
        assert graph.evaluations["X"].replacement is CriteriaGraph.END

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
        assert graph.starting_evaluations("EQ_TRUE") == ["EQ"]
        with pytest.raises(CriteriaGraphError, match="EQ is an evaluation node"):
            graph.starting_evaluations("EQ")
        with pytest.raises(CriteriaGraphError, match="Unknown criterion NOPE"):
            graph.starting_evaluations("NOPE")

    def test_criterion_without_evaluations_cannot_be_decided(self):
        graph = CriteriaGraph("g")
        graph.add_criterion_node("C", "s", "d")
        with pytest.raises(CriteriaGraphError, match="No evaluation leads to criterion C"):
            graph.generate_feedback("x", "C")

    def test_sufficiencies_move_the_start_to_the_sufficient_criteria(self):
        graph = equality_graph()
        graph.add_sufficiencies("SIMPLIFIED", ["EQ_TRUE"])
        assert graph.starting_evaluations("SIMPLIFIED_TRUE") == ["EQ"]

    def test_generate_feedback_follows_reached_criteria(self):
        feedback = equality_graph().generate_feedback("response", "EQ_TRUE")
        assert list(feedback) == ["EQ_TRUE", "SIMPLIFIED_TRUE"]

    def test_evaluations_receive_the_response(self):
        seen = []
        graph = CriteriaGraph("g")
        graph.add_evaluation_node("E", "s", "d", evaluate=lambda response: seen.append(response) or {})
        graph.attach("E", "C", summary="c", details="c")
        graph.generate_feedback("x + 1", "C")
        assert seen == ["x + 1"]

    def test_replaced_evaluations_are_skipped(self):
        graph = equality_graph()
        graph.evaluations["SIMPLIFIED"].replacement = CriteriaGraph.END
        assert list(graph.generate_feedback("response", "EQ_TRUE")) == ["EQ_TRUE"]

    def test_replacement_chains_are_followed(self):
        graph = equality_graph()
        graph.attach("EQ_FALSE", "OTHER", summary="other", details="other", evaluate=returns("OTHER_TRUE"))
        graph.attach("OTHER", "OTHER_TRUE", summary="yes", details="yes")
        graph.evaluations["SIMPLIFIED"].replacement = graph.evaluations["OTHER"]
        graph.evaluations["OTHER"].replacement = CriteriaGraph.END
        assert list(graph.generate_feedback("response", "EQ_TRUE")) == ["EQ_TRUE"]

    def test_replacement_cycles_terminate(self):
        graph = equality_graph()
        graph.attach("EQ_FALSE", "OTHER", summary="other", details="other", evaluate=returns("OTHER_TRUE"))
        graph.attach("OTHER", "OTHER_TRUE", summary="yes", details="yes")
        graph.evaluations["SIMPLIFIED"].replacement = graph.evaluations["OTHER"]
        graph.evaluations["OTHER"].replacement = graph.evaluations["SIMPLIFIED"]
        assert list(graph.generate_feedback("response", "EQ_TRUE")) == ["EQ_TRUE"]

    def test_evaluate_must_return_a_mapping(self):
        graph = CriteriaGraph("g")
        graph.add_evaluation_node("E", "s", "d", evaluate=lambda response: ["C"])
        graph.attach("E", "C", summary="c", details="c")
        with pytest.raises(CriteriaGraphError, match=r"E must return a mapping .* got list"):
            graph.generate_feedback("x", "C")

    def test_unknown_criterion_reported_by_evaluate(self):
        graph = CriteriaGraph("g")
        graph.add_evaluation_node("E", "s", "d", evaluate=returns("TYPO"))
        graph.attach("E", "C", summary="c", details="c")
        with pytest.raises(CriteriaGraphError, match="E reported unknown criteria: TYPO"):
            graph.generate_feedback("x", "C")

    def test_unknown_sufficiency(self):
        graph = CriteriaGraph("g")
        graph.add_evaluation_node("E", "s", "d", sufficiencies=["NOPE"])
        graph.attach("E", "C", summary="c", details="c")
        with pytest.raises(CriteriaGraphError, match="sufficiency NOPE, which is not a criterion"):
            graph.starting_evaluations("C")

    def test_resolve_feedback_unknown_tag(self):
        graph = equality_graph()
        with pytest.raises(CriteriaGraphError, match="Unknown criterion NOPE"):
            graph.resolve_feedback({"NOPE": None})
        assert graph.resolve_feedback({"NOPE": None}, custom_feedback={"NOPE": " custom "}) == [("NOPE", "custom")]

    def test_evaluation_without_evaluate_function(self):
        graph = CriteriaGraph("g")
        graph.add_evaluation_node("E", "s", "d")
        graph.attach("E", "C", summary="c", details="c")
        with pytest.raises(CriteriaGraphError, match="no evaluate function"):
            graph.generate_feedback("x", "C")


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

    def test_children_are_in_attachment_order(self):
        graph = CriteriaGraph("g")
        graph.add_evaluation_node("E", "e", "d")
        for criterion in "ABC":
            graph.attach("E", criterion, summary=criterion, details=criterion)
        assert [child.label for child in graph.build_tree("E").children] == ["A", "B", "C"]

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
        assert "N_0_1 -.-> N_1_0" in lines  # SIMPLIFIED -.-> EQ_TRUE, by node id

    def test_mermaid_escapes_quotes(self):
        graph = CriteriaGraph("g")
        graph.add_output_node("O", "s", 'say "hi"')
        assert 'N_2_0{{"O<br/>---<br/>say #quot;hi#quot;"}}' in graph.to_mermaid().split("\n\t")

    def test_tree_mermaid_ids_are_safe_and_text_escaped(self):
        graph = CriteriaGraph("g")
        graph.add_evaluation_node("x = y", 'is "x" y?', "d")
        mermaid = graph.build_tree("x = y").to_mermaid()
        assert 'x___y_0>"is #quot;x#quot; y?"]' in mermaid.split("\n\t")
