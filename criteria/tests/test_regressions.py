"""Regression tests for bugs carried over from the v0.1 extraction."""

import os
import subprocess
import sys

import pytest

from lambdafeedback.criteria import (
    CriteriaEvaluationError,
    CriteriaGraph,
    CriterionNode,
    EvaluationNode,
    build_criteria_parser,
)


def small_graph():
    graph = CriteriaGraph("g")
    graph.add_evaluation_node("E1", "eval", "evaluate E1")
    graph.attach_new_criterion("E1", "C1", "crit", "criterion C1")
    graph.add_output_node("OUT", "out", "done")
    graph.attach("C1", "OUT")
    return graph


class TestTreeRendering:
    def test_mermaid_does_not_consume_the_tree(self):
        tree = small_graph().build_tree("E1")
        first = tree.to_mermaid()
        assert len(tree.children) == 1
        assert tree.to_mermaid() == first
        assert "C1" in first and "OUT" in first


class TestCriteriaParser:
    def test_reserved_words_do_not_leak_between_parsers(self):
        build_criteria_parser({"learner": {"response": None}})
        parser = build_criteria_parser({"task": {"answer": None}})
        labels = [token.label for token in parser.scan("response = answer")]
        assert labels == ["OTHER", "EQUALITY", "RESERVED"]


class TestGraph:
    def test_build_tree_rejects_unknown_evaluation(self):
        with pytest.raises(ValueError, match="Unknown evaluation node NOPE"):
            small_graph().build_tree("NOPE")

    def test_add_node_keeps_evaluate_and_feedback_generator(self):
        def evaluate(response):
            return {}

        def feedback(inputs):
            return "text"

        graph = CriteriaGraph("g")
        graph.add_node(EvaluationNode("E", "eval", "details", evaluate))
        graph.add_node(CriterionNode("C", "crit", "details", feedback_string_generator=feedback))
        assert graph.evaluations["E"].evaluate is evaluate
        assert graph.criteria["C"].feedback_string_generator is feedback

    def test_nodes_are_hashable_and_comparable_to_anything(self):
        node = small_graph().evaluations["E1"]
        assert node in {node}
        assert node != "E1"

    def test_failing_evaluation_is_reported_without_printing(self, capsys):
        def broken(response):
            raise RuntimeError("boom")

        graph = CriteriaGraph("g")
        graph.add_evaluation_node("E1", "eval", "details", evaluate=broken)
        graph.attach_new_criterion("E1", "E1_TRUE", "true", "true")
        with pytest.raises(CriteriaEvaluationError, match="E1") as info:
            graph.generate_feedback("x", "E1_TRUE")
        assert isinstance(info.value.__cause__, RuntimeError)
        assert capsys.readouterr().out == ""


DETERMINISM_SCRIPT = """
from lambdafeedback.criteria import CriteriaGraph
g = CriteriaGraph("g")
g.add_evaluation_node("START", "s", "d", evaluate=lambda r: {"A": None, "B": None, "C": None})
for c in "ABC":
    g.attach_new_criterion("START", c, c, c)
    g.attach_new_evaluation(c, "E" + c, c, c, evaluate=(lambda c: lambda r: {c + "_OK": None})(c))
    g.attach_new_criterion("E" + c, c + "_OK", c, c)
print(list(g.generate_feedback("r", "A")))
print(g.to_mermaid())
"""


class TestDeterminism:
    def test_feedback_and_mermaid_do_not_depend_on_the_hash_seed(self):
        outputs = {
            subprocess.run(
                [sys.executable, "-c", DETERMINISM_SCRIPT],
                env={**os.environ, "PYTHONHASHSEED": str(seed)},
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            for seed in (1, 2, 3, 4)
        }
        assert len(outputs) == 1
        assert outputs.pop().splitlines()[0] == "['A', 'B', 'C', 'A_OK', 'B_OK', 'C_OK']"

    def test_cyclic_sufficiencies_terminate(self):
        graph = CriteriaGraph("g")
        graph.add_evaluation_node("E1", "e1", "d", sufficiencies=["C2"])
        graph.attach_new_criterion("E1", "C1", "c1", "d")
        graph.attach_new_evaluation("C1", "E2", "e2", "d", sufficiencies=["C1"])
        graph.attach_new_criterion("E2", "C2", "c2", "d")
        assert list(graph.starting_evaluations("C2")) == ["E2"]


@pytest.mark.parametrize(("text", "reserved"), [("x.y", True), ("xzy", False), ("f(x)", True)])
def test_reserved_names_are_matched_literally(text, reserved):
    # Reserved names were used as regular expressions: "x.y" matched "xzy" and "f(x)" never matched itself.
    parser = build_criteria_parser({"learner": {"x.y": None, "f(x)": None}})
    assert (parser.scan(text)[0].label == "RESERVED") is reserved
