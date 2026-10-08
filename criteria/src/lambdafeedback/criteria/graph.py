"""The criteria graph: evaluations, the criteria they establish, and outputs."""

from __future__ import annotations

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


class CriteriaGraph:
    """A graph of evaluations, the criteria they establish, and outputs.

    Evaluations point to criteria; criteria point to further evaluations or
    to outputs. ``generate_feedback`` walks the graph from the evaluations
    leading to a main criterion and collects every criterion reached;
    ``export_feedback`` turns those into feedback on a result object.

    To export feedback differently, subclass and override ``export_feedback``
    (building on ``resolve_feedback`` for the text).
    """

    END: ClassVar[OutputNode] = OutputNode("END", "END", "Evaluation completed.")
    """Conventional terminal output; add it with ``graph.add_node(CriteriaGraph.END)``."""

    def __init__(self, identifier: str) -> None:
        """Create an empty graph named ``identifier`` (used to tell graphs apart, e.g. in test data)."""
        self.identifier = identifier
        self.evaluations: dict[str, EvaluationNode] = {}
        self.criteria: dict[str, CriterionNode] = {}
        self.outputs: dict[str, OutputNode] = {}
        # Evaluation label -> criteria whose evaluations can stand in for it
        # when choosing where to start (see starting_evaluations).
        self.sufficiencies: dict[str, list[str] | None] = {}

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def add_evaluation_node(
        self,
        label: str,
        summary: str,
        details: str,
        sufficiencies: Iterable[str] | None = None,
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
        node = EvaluationNode(label, summary, details, evaluate)
        self.evaluations[label] = node
        self.sufficiencies[label] = list(sufficiencies) if sufficiencies is not None else None
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

    def _check_label_is_free(self, label: str) -> None:
        # Labels are unique across kinds: sufficiencies and renderings key on them.
        for kind, nodes in (("Evaluation", self.evaluations), ("Criterion", self.criteria), ("Output", self.outputs)):
            if label in nodes:
                raise CriteriaGraphError(f"{kind} node {label} is already defined.")

    def add_node(self, node: Node) -> None:
        """Add a copy of ``node`` (e.g. ``CriteriaGraph.END``) to this graph, without its edges."""
        if isinstance(node, EvaluationNode):
            copy = self.add_evaluation_node(node.label, node.summary, node.details, evaluate=node.evaluate)
            copy.replacement = node.replacement
        elif isinstance(node, CriterionNode):
            self.add_criterion_node(
                node.label, node.summary, node.details, feedback_string_generator=node.feedback_string_generator
            )
        elif isinstance(node, OutputNode):
            self.add_output_node(node.label, node.summary, node.details)
        else:
            raise CriteriaGraphError("Can only add evaluation, criterion or output nodes to criteria graph.")

    def attach(
        self,
        source_label: str,
        target_label: str,
        summary: str | None = None,
        details: str | None = None,
        sufficiencies: Iterable[str] | None = None,
        evaluate: Evaluate | None = None,
        feedback_string_generator: FeedbackStringGenerator | None = None,
    ) -> None:
        """Add an edge from ``source_label`` to ``target_label``.

        Evaluations attach to criteria, criteria to evaluations or outputs. If
        the target doesn't exist it is created (of the kind the source leads
        to), which requires ``summary`` and ``details``. A new criterion takes
        ``feedback_string_generator``; a new evaluation takes ``sufficiencies``
        and ``evaluate``. To attach to an existing node, pass none of these.

        Raises ``CriteriaGraphError`` if the source is unknown or an output,
        the target is of the wrong kind or is unknown without ``summary`` and
        ``details``, a keyword doesn't apply to the new node's kind, keywords
        are given for an existing target, or the edge already exists.
        """
        source: Node | None = self.evaluations.get(source_label) or self.criteria.get(source_label)
        if source is None:
            if source_label in self.outputs:
                raise CriteriaGraphError(f"{source_label} is an output node. Output nodes cannot have outgoing edges.")
            raise CriteriaGraphError(f"Unknown node {source_label}.")

        target: Node | None
        wrong_kind: Mapping[str, Node]
        if isinstance(source, EvaluationNode):
            target, wrong_kind = self.criteria.get(target_label), self.evaluations
            kind, other_kind = "evaluation", "criterion"
        else:
            target = self.evaluations.get(target_label) or self.outputs.get(target_label)
            wrong_kind, kind, other_kind = self.criteria, "criterion", "evaluation"

        if target is None:
            if isinstance(source, EvaluationNode) and target_label in self.outputs:
                raise CriteriaGraphError(
                    f"{target_label} is an output node. Only criterion nodes can be attached to evaluation nodes."
                )
            if target_label in wrong_kind:
                raise CriteriaGraphError(
                    f"Both {source_label} and {target_label} are {kind} nodes. "
                    f"Only {other_kind} nodes can be attached to {kind} nodes."
                )
            if summary is None or details is None:
                raise CriteriaGraphError(
                    f"Unknown node {target_label}. If you wish to create a new node, summary and details must be "
                    "specified."
                )
            if isinstance(source, EvaluationNode):
                if sufficiencies is not None:
                    raise CriteriaGraphError("Criterion nodes cannot have sufficiencies.")
                if evaluate is not None:
                    raise CriteriaGraphError(
                        f"{target_label} is a criterion node, criterion nodes cannot have an evaluate function."
                    )
                target = self.add_criterion_node(target_label, summary, details, feedback_string_generator)
            else:
                if feedback_string_generator is not None:
                    raise CriteriaGraphError(
                        f"{target_label} is an evaluation node, evaluation nodes cannot generate feedback strings."
                    )
                target = self.add_evaluation_node(target_label, summary, details, sufficiencies, evaluate)
        elif any(
            option is not None for option in (summary, details, sufficiencies, evaluate, feedback_string_generator)
        ):
            raise CriteriaGraphError(
                f"{target_label} already exists; summary, details and node options only apply when attach creates "
                "the target."
            )

        edge = Edge(source, target)
        if edge in source.outgoing:
            raise CriteriaGraphError(f"{target_label} is already attached to {source_label}.")
        source.outgoing.append(edge)
        target.incoming.append(edge)

    def add_sufficiencies(self, source_label: str, sufficiencies: Iterable[str]) -> None:
        """Add criteria whose evaluations can stand in for evaluation ``source_label``.

        Criteria already listed are skipped. Raises ``CriteriaGraphError`` if
        ``source_label`` is not an evaluation.
        """
        if source_label not in self.evaluations:
            raise CriteriaGraphError(
                f"Unknown evaluation node {source_label}. Only evaluation nodes can have sufficiencies."
            )
        existing = self.sufficiencies.get(source_label)
        if existing is None:
            existing = self.sufficiencies[source_label] = []
        for sufficiency in sufficiencies:
            if sufficiency not in existing:
                existing.append(sufficiency)

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
            sufficiencies = self.sufficiencies.get(candidate)
            if sufficiencies is None:
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
        Evaluations with a ``replacement`` are skipped in favour of it, following
        chains of replacements; replacing with an output (e.g. ``END``) stops there.

        Raises ``CriteriaEvaluationError`` (chaining the cause) if an
        ``evaluate`` function fails, and ``CriteriaGraphError`` if an evaluation
        has no ``evaluate`` function, returns something other than a mapping or
        reports a criterion not in the graph, and for the reasons
        ``starting_evaluations`` does.
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
                label = node.replacement.label
                node = self.evaluations.get(label)
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
