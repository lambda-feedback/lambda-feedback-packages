"""The criteria graph: evaluations, the criteria they establish, and outputs."""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Collection, Iterable, Mapping
from typing import Any, ClassVar

from .errors import CriteriaEvaluationError, CriteriaGraphError
from .nodes import (
    CriterionNode,
    Edge,
    Evaluate,
    EvaluationNode,
    FeedbackStringGenerator,
    Node,
    OutputNode,
    ReachedCriteria,
    ResultLike,
    no_feedback,
)
from .render import graph_to_json, graph_to_mermaid
from .tree import CriteriaTree, build_tree

logger = logging.getLogger(__name__)


class CriteriaGraph:
    """A graph of evaluations, the criteria they establish, and outputs.

    Evaluations point to criteria; criteria point to further evaluations or
    to outputs. ``generate_feedback`` walks the graph from the evaluations
    leading to a main criterion and collects every criterion reached;
    ``export_feedback`` turns those into feedback on a result object.

    To export feedback differently, subclass and override ``export_feedback``
    (building on ``resolve_feedback`` for the text).
    """

    END_LABEL: ClassVar[str] = "END"
    """Label of the conventional terminal output that :meth:`add_end_node` adds."""

    def __init__(self, identifier: str) -> None:
        """Create an empty graph named ``identifier`` (used to tell graphs apart, e.g. in test data)."""
        self.identifier = identifier
        self.evaluations: dict[str, EvaluationNode] = {}
        self.criteria: dict[str, CriterionNode] = {}
        self.outputs: dict[str, OutputNode] = {}

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def add_evaluation_node(
        self,
        label: str,
        summary: str,
        details: str,
        sufficiencies: Iterable[str] = (),
        evaluate: Evaluate | None = None,
    ) -> EvaluationNode:
        """Add an evaluation node and return it.

        ``evaluate(response)`` reports the criteria that hold (see ``Evaluate``);
        it may be left unset while building, but ``generate_feedback`` raises if
        it reaches the node without one. ``sufficiencies`` lists criteria whose
        evaluations can stand in for this one (see ``starting_evaluations``).

        Raises ``CriteriaGraphError`` if a node labelled ``label`` exists.
        """
        self._check_label_is_free(label)
        node = EvaluationNode(label, summary, details, evaluate, sufficiencies=tuple(dict.fromkeys(sufficiencies)))
        self.evaluations[label] = node
        return node

    def add_criterion_node(
        self,
        label: str,
        summary: str,
        details: str,
        feedback_string_generator: FeedbackStringGenerator | None = None,
    ) -> CriterionNode:
        """Add a criterion node and return it.

        ``feedback_string_generator`` renders the criterion's feedback text from
        the inputs its evaluation reports; by default the criterion has no text.

        Raises ``CriteriaGraphError`` if a node labelled ``label`` exists.
        """
        self._check_label_is_free(label)
        node = CriterionNode(label, summary, details, feedback_string_generator or no_feedback)
        self.criteria[label] = node
        return node

    def add_output_node(self, label: str, summary: str, details: str) -> OutputNode:
        """Add a terminal output node and return it.

        Raises ``CriteriaGraphError`` if a node labelled ``label`` exists.
        """
        self._check_label_is_free(label)
        node = OutputNode(label, summary, details)
        self.outputs[label] = node
        return node

    def add_end_node(self) -> OutputNode:
        """Add the conventional terminal output, labelled :attr:`END_LABEL`, and return it."""
        return self.add_output_node(self.END_LABEL, "END", "Evaluation completed.")

    def _check_label_is_free(self, label: str) -> None:
        # Labels are unique across kinds: sufficiencies and renderings key on them.
        for kind, nodes in (("Evaluation", self.evaluations), ("Criterion", self.criteria), ("Output", self.outputs)):
            if label in nodes:
                raise CriteriaGraphError(f"{kind} node {label} is already defined.")

    def add_node(self, node: Node) -> None:
        """Add a copy of ``node`` (e.g. from another graph) to this graph, without its edges."""
        node.copy_into(self)

    def attach(self, source_label: str, target_label: str) -> None:
        """Add an edge between existing nodes: evaluation to criterion, or criterion to evaluation or output.

        To create the target as well, use :meth:`attach_new_criterion` or
        :meth:`attach_new_evaluation`. Raises ``CriteriaGraphError`` if either
        node is unknown, the target is of the wrong kind, or the edge exists.
        """
        source = self._source(source_label)
        target: Node | None = (
            self.evaluations.get(target_label) or self.criteria.get(target_label) or self.outputs.get(target_label)
        )
        if target is None:
            raise CriteriaGraphError(f"Unknown node {target_label}.")
        source.check_target(target)
        edge = Edge(source, target)
        if edge in source.outgoing:
            raise CriteriaGraphError(f"{target_label} is already attached to {source_label}.")
        source.outgoing.append(edge)
        target.incoming.append(edge)

    def attach_new_criterion(
        self,
        evaluation_label: str,
        label: str,
        summary: str,
        details: str,
        feedback_string_generator: FeedbackStringGenerator | None = None,
    ) -> CriterionNode:
        """Add a criterion node (see :meth:`add_criterion_node`) reached from evaluation ``evaluation_label``."""
        if not isinstance(self._source(evaluation_label), EvaluationNode):
            raise CriteriaGraphError(f"{evaluation_label} is a criterion node; criteria follow evaluation nodes.")
        node = self.add_criterion_node(label, summary, details, feedback_string_generator)
        self.attach(evaluation_label, label)
        return node

    def attach_new_evaluation(
        self,
        criterion_label: str,
        label: str,
        summary: str,
        details: str,
        sufficiencies: Iterable[str] = (),
        evaluate: Evaluate | None = None,
    ) -> EvaluationNode:
        """Add an evaluation node (see :meth:`add_evaluation_node`) reached from criterion ``criterion_label``."""
        if not isinstance(self._source(criterion_label), CriterionNode):
            raise CriteriaGraphError(f"{criterion_label} is an evaluation node; evaluations follow criterion nodes.")
        node = self.add_evaluation_node(label, summary, details, sufficiencies, evaluate)
        self.attach(criterion_label, label)
        return node

    def _source(self, label: str) -> EvaluationNode | CriterionNode:
        """The node edges can start from (an evaluation or criterion) labelled ``label``."""
        source = self.evaluations.get(label) or self.criteria.get(label)
        if source is None:
            if label in self.outputs:
                raise CriteriaGraphError(f"{label} is an output node. Output nodes cannot have outgoing edges.")
            raise CriteriaGraphError(f"Unknown node {label}.")
        return source

    def add_sufficiencies(self, source_label: str, sufficiencies: Iterable[str]) -> None:
        """Add criteria whose evaluations can stand in for evaluation ``source_label``.

        Criteria already listed are skipped. Raises ``CriteriaGraphError`` if
        ``source_label`` is not an evaluation.
        """
        node = self.evaluations.get(source_label)
        if node is None:
            raise CriteriaGraphError(
                f"Unknown evaluation node {source_label}. Only evaluation nodes can have sufficiencies."
            )
        node.sufficiencies = tuple(dict.fromkeys([*node.sufficiencies, *sufficiencies]))

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def starting_evaluations(self, criterion: str) -> list[str]:
        """The evaluations to start from to decide ``criterion``.

        These are the evaluations leading to ``criterion``, except that
        evaluations with sufficiencies are replaced by the evaluations leading
        to those sufficient criteria, recursively.

        Raises ``CriteriaGraphError`` if ``criterion`` is not a criterion of the
        graph, no evaluation leads to it, or a sufficiency names a label that is
        not a criterion.
        """
        if criterion not in self.criteria:
            if criterion in self.evaluations:
                raise CriteriaGraphError(
                    f"{criterion} is an evaluation node; starting evaluations are found for criteria."
                )
            raise CriteriaGraphError(f"Unknown criterion {criterion}.")
        base = list(dict.fromkeys(edge.source.label for edge in self.criteria[criterion].incoming))
        if not base:
            raise CriteriaGraphError(f"No evaluation leads to criterion {criterion}.")
        # Ordered worklist (not a set): the result must not depend on the hash seed.
        starting: list[str] = []
        candidates = deque(base)
        seen: set[str] = set()
        while candidates:
            candidate = candidates.popleft()
            if candidate in seen:
                continue  # sufficiencies can form cycles
            seen.add(candidate)
            node = self.evaluations.get(candidate)
            sufficiencies = () if node is None else node.sufficiencies
            if not sufficiencies:
                starting.append(candidate)
            else:
                for sufficiency in sufficiencies:
                    sufficient = self.criteria.get(sufficiency)
                    if sufficient is None:
                        raise CriteriaGraphError(
                            f"Evaluation node {candidate} has sufficiency {sufficiency}, which is not a criterion."
                        )
                    candidates.extend(edge.source.label for edge in sufficient.incoming)
        return starting or base

    def build_tree(self, starting_evaluation: str, main_criteria: Collection[str] = ()) -> CriteriaTree:
        """The graph unrolled from ``starting_evaluation`` as a tree (for display)."""
        return build_tree(self, starting_evaluation, main_criteria)

    def trees(self, criterion: str) -> list[CriteriaTree]:
        """One tree per starting evaluation for ``criterion``, with ``criterion`` marked as the main criterion."""
        return [self.build_tree(start, main_criteria=[criterion]) for start in self.starting_evaluations(criterion)]

    def generate_feedback(self, response: Any, main_criterion: str) -> ReachedCriteria:
        """Run the evaluations reachable from the starting evaluations for criterion ``main_criterion``.

        Returns every criterion reached, mapped to the inputs for its feedback
        text, in the order reached (breadth-first, in attachment order); pass
        it to ``export_feedback`` or ``resolve_feedback`` for the text.
        Evaluations with a ``replacement`` are skipped in favour of the node it
        names, following chains of replacements; replacing with an output (e.g.
        ``END_LABEL``) stops there.

        Raises ``CriteriaEvaluationError`` (chaining the cause) if an
        ``evaluate`` function fails, and ``CriteriaGraphError`` if an evaluation
        has no ``evaluate`` function, returns something other than a mapping or
        reports a criterion not in the graph, if a replacement names neither an
        evaluation nor an output, and for the reasons ``starting_evaluations`` does.
        """
        queue = deque(self.starting_evaluations(main_criterion))
        visited: set[str] = set()
        feedback: dict[str, Mapping[str, Any] | None] = {}
        while queue:
            label = queue.popleft()
            node = self.evaluations.get(label)
            # Follow replacements; `visited` also stops replacement cycles.
            while node is not None and node.replacement is not None and label not in visited:
                visited.add(label)
                logger.debug("evaluation %s is replaced by %s", label, node.replacement)
                label = node.replacement
                node = self.evaluations.get(label)
                if node is None and label not in self.outputs:
                    raise CriteriaGraphError(f"Replacement {label} is neither an evaluation nor an output node.")
            if label in visited or label not in self.evaluations:
                continue
            visited.add(label)
            evaluate = self.evaluations[label].evaluate
            if evaluate is None:
                raise CriteriaGraphError(f"Evaluation node {label} has no evaluate function.")
            try:
                results = evaluate(response)
            except Exception as exc:
                raise CriteriaEvaluationError(label) from exc
            if not isinstance(results, Mapping):
                raise CriteriaGraphError(
                    f"Evaluation node {label} must return a mapping of criterion labels to feedback inputs, "
                    f"got {type(results).__name__}."
                )
            unknown = [criterion for criterion in results if criterion not in self.criteria]
            if unknown:
                raise CriteriaGraphError(f"Evaluation node {label} reported unknown criteria: {', '.join(unknown)}.")
            logger.debug("evaluation %s reported %s", label, list(results))
            feedback.update(results)
            for criterion in results:
                queue.extend(edge.target.label for edge in self.criteria[criterion].outgoing)
        return feedback

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------

    def resolve_feedback(
        self,
        reached: ReachedCriteria,
        custom_feedback: Mapping[str, str] | None = None,
    ) -> list[tuple[str, str]]:
        """Feedback text for each reached criterion, as ``(tag, text)`` pairs.

        ``reached`` maps criterion labels to the inputs for their feedback
        string generators (as returned by ``generate_feedback``).
        ``custom_feedback`` overrides the text for given tags. Text is stripped,
        and a generator returning ``None`` gives ``""``: the tag still counts as
        reached, it just has nothing to say.

        Raises ``CriteriaGraphError`` for a tag that is neither a criterion of
        the graph nor in ``custom_feedback``.
        """
        custom_feedback = custom_feedback or {}
        resolved = []
        for tag, inputs in reached.items():
            if tag in custom_feedback:
                text: str | None = custom_feedback[tag]
            elif tag in self.criteria:
                text = self.criteria[tag].feedback_string_generator(inputs or {})
            else:
                raise CriteriaGraphError(f"Unknown criterion {tag}, and no custom feedback was given for it.")
            resolved.append((tag, (text or "").strip()))
        return resolved

    def export_feedback(
        self,
        result: ResultLike,
        reached: ReachedCriteria,
        custom_feedback: Mapping[str, str] | None = None,
    ) -> None:
        """Add the feedback for each reached criterion to ``result``.

        Tags already on the result are skipped, so exporting several graphs'
        feedback into one result keeps the first text for a shared tag. Blank
        feedback is added as ``""`` so that the tag is still recorded.

        Override in a subclass to export feedback differently.
        """
        existing = set(result.tags or ())
        for tag, text in self.resolve_feedback(reached, custom_feedback):
            if tag not in existing:
                result.add_feedback(tag, text)
                existing.add(tag)

    @staticmethod
    def test_data(graphs: Mapping[str, CriteriaGraph]) -> dict[str, dict[str, str]]:
        """The criteria-graph payload for a result's test data (JSON and mermaid per graph).

        Merge it into the serialised result when test data is requested, e.g.
        ``{**result.to_dict(include_test_data=True), **CriteriaGraph.test_data(graphs)}``.
        """
        return {
            "criteria_graphs": {name: graph.to_json() for name, graph in graphs.items()},
            "criteria_graphs_vis": {name: graph.to_mermaid() for name, graph in graphs.items()},
        }

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def to_json(self) -> str:
        """The graph's nodes, edges and sufficiencies as a JSON string."""
        return graph_to_json(self)

    def to_mermaid(self) -> str:
        """Mermaid flowchart source for the graph."""
        return graph_to_mermaid(self)
