"""Tests for CriteriaGraph's feedback methods (which replace evaluation_result's criteria support)."""

import json

import pytest

from lambdafeedback.criteria import CriteriaGraph


class RecordingResult:
    """Minimal ResultLike: tags derive from the feedback added, like lf_toolkit's Result."""

    def __init__(self):
        self.feedback = {}

    @property
    def tags(self):
        return list(self.feedback)

    def add_feedback(self, tag, feedback):
        self.feedback.setdefault(tag, []).append(feedback)


def build_graph(graph):
    graph.add_evaluation_node("EQ", "response = answer", "compare")
    graph.attach_new_criterion("EQ", "EQ_TRUE", "true", "true", feedback_string_generator=lambda inputs: " Correct! ")
    graph.attach_new_criterion(
        "EQ", "EQ_FALSE", "false", "false", feedback_string_generator=lambda inputs: inputs["why"]
    )
    graph.attach_new_criterion("EQ", "EQ_SILENT", "silent", "silent", feedback_string_generator=lambda inputs: None)
    return graph


def graph_with_feedback():
    return build_graph(CriteriaGraph("g"))


class TestResolveFeedback:
    def test_generators_receive_inputs_and_text_is_stripped(self):
        resolved = graph_with_feedback().resolve_feedback({"EQ_TRUE": None, "EQ_FALSE": {"why": "x != y"}})
        assert resolved == [("EQ_TRUE", "Correct!"), ("EQ_FALSE", "x != y")]

    def test_none_feedback_resolves_to_empty_text(self):
        assert graph_with_feedback().resolve_feedback({"EQ_SILENT": None}) == [("EQ_SILENT", "")]

    def test_custom_feedback_overrides_generator(self):
        resolved = graph_with_feedback().resolve_feedback({"EQ_TRUE": None}, custom_feedback={"EQ_TRUE": "Well done"})
        assert resolved == [("EQ_TRUE", "Well done")]


class TestExportFeedback:
    def test_records_every_tag_including_blank_feedback(self):
        result = RecordingResult()
        graph_with_feedback().export_feedback(result, {"EQ_TRUE": None, "EQ_SILENT": None})
        assert result.tags == ["EQ_TRUE", "EQ_SILENT"]
        assert result.feedback == {"EQ_TRUE": ["Correct!"], "EQ_SILENT": [""]}

    def test_tags_already_on_the_result_are_skipped(self):
        result = RecordingResult()
        result.add_feedback("EQ_TRUE", "first")
        graph_with_feedback().export_feedback(result, {"EQ_TRUE": None})
        assert result.feedback == {"EQ_TRUE": ["first"]}

    def test_subclass_can_override_export(self):
        class DictExportGraph(CriteriaGraph):
            def export_feedback(self, result, reached, custom_feedback=None):
                result.update(self.resolve_feedback(reached, custom_feedback))

        graph = build_graph(DictExportGraph("g"))
        exported = {}
        graph.export_feedback(exported, {"EQ_TRUE": None, "EQ_SILENT": None}, custom_feedback={"EQ_SILENT": "hush"})
        assert exported == {"EQ_TRUE": "Correct!", "EQ_SILENT": "hush"}


def test_test_data():
    graph = graph_with_feedback()
    data = CriteriaGraph.test_data({"main": graph})
    assert set(data) == {"criteria_graphs", "criteria_graphs_vis"}
    assert "EQ" in json.loads(data["criteria_graphs"]["main"])["evaluations"]
    assert data["criteria_graphs_vis"]["main"].startswith("flowchart TD")


class TestLfToolkitCompatibility:
    """export_feedback is written against a Protocol; check the real lf_toolkit Result fits it."""

    def test_feedback_lands_on_an_lf_toolkit_result(self):
        evaluation = pytest.importorskip("lf_toolkit.evaluation")
        result = evaluation.Result()
        graph_with_feedback().export_feedback(result, {"EQ_TRUE": None, "EQ_FALSE": {"why": "x != y"}})
        assert result.tags == ["EQ_TRUE", "EQ_FALSE"]
        assert result.feedback == "Correct!<br>x != y"
