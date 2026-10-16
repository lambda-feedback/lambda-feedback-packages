"""Nodes and edges of a criteria graph.

A criteria graph alternates between *evaluation* nodes, which run a check and
report which criteria hold, and *criterion* nodes, which record an outcome
and lead to further evaluations or to *output* nodes.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol, TypeAlias

from .errors import CriteriaGraphError

if TYPE_CHECKING:
    from .graph import CriteriaGraph

ReachedCriteria: TypeAlias = Mapping[str, Mapping[str, Any] | None]
"""``{criterion_label: feedback_inputs_or_None}`` for the criteria that hold (or were reached)."""

Evaluate: TypeAlias = Callable[[Any], ReachedCriteria]
"""``evaluate(response) -> {criterion_label: feedback_inputs_or_None}`` for the criteria that hold."""

FeedbackStringGenerator: TypeAlias = Callable[[Mapping[str, Any]], str | None]
"""Renders a criterion's feedback text from the inputs its evaluation reported."""

NodeKind: TypeAlias = Literal["evaluation", "criterion", "output"]


class ResultLike(Protocol):
    """The part of a result object ``CriteriaGraph.export_feedback`` needs (``lf_toolkit.evaluation.Result`` fits)."""

    @property
    def tags(self) -> list[str] | None:
        """The tags already on the result, if any."""
        ...

    def add_feedback(self, tag: str, feedback: str) -> None:
        """Record ``feedback`` text under ``tag``."""
        ...


def no_feedback(inputs: Mapping[str, Any]) -> None:
    """Default feedback generator: the criterion has nothing to say."""
    return None


@dataclass(eq=False)
class Node:
    """A graph node. Nodes compare (and hash) by identity; within a graph, labels are unique.

    Each kind of node (the subclasses) sets ``KIND`` and ``STYLE`` and says
    which edges it allows (:meth:`check_target`); a plain ``Node`` has no kind
    and can't be added to a graph.
    """

    KIND: ClassVar[NodeKind | None] = None
    STYLE: ClassVar[tuple[str, str] | None] = None
    """Mermaid shape (opening, closing)."""

    label: str
    summary: str
    details: str
    incoming: list[Edge] = field(default_factory=list, init=False, repr=False)
    outgoing: list[Edge] = field(default_factory=list, init=False, repr=False)

    def copy_into(self, graph: CriteriaGraph) -> Node:
        """Add a copy of this node, without its edges, to ``graph`` and return the copy."""
        raise CriteriaGraphError("Can only add evaluation, criterion or output nodes to criteria graph.")

    def check_target(self, target: Node) -> None:
        """Raise :class:`CriteriaGraphError` unless an edge may lead from this node to ``target``."""
        raise CriteriaGraphError(f"{self.label} can't have outgoing edges.")


@dataclass(eq=False)
class EvaluationNode(Node):
    """Runs ``evaluate`` on the response; the criteria it reports lead onwards.

    Setting ``replacement`` to another node's label (e.g.
    ``CriteriaGraph.END_LABEL``) disables the evaluation: feedback generation
    goes to that node instead. ``sufficiencies`` lists criteria whose
    evaluations can stand in for this one when choosing where to start (see
    ``CriteriaGraph.starting_evaluations``).
    """

    KIND: ClassVar[NodeKind | None] = "evaluation"
    STYLE: ClassVar[tuple[str, str] | None] = ("([", "])")

    evaluate: Evaluate | None = None
    replacement: str | None = None
    sufficiencies: tuple[str, ...] = ()

    def copy_into(self, graph: CriteriaGraph) -> EvaluationNode:
        copy = graph.add_evaluation_node(self.label, self.summary, self.details, self.sufficiencies, self.evaluate)
        copy.replacement = self.replacement
        return copy

    def check_target(self, target: Node) -> None:
        if target.KIND == "output":
            raise CriteriaGraphError(
                f"{target.label} is an output node. Only criterion nodes can be attached to evaluation nodes."
            )
        if target.KIND == "evaluation":
            raise CriteriaGraphError(
                f"Both {self.label} and {target.label} are evaluation nodes. "
                "Only criterion nodes can be attached to evaluation nodes."
            )


@dataclass(eq=False)
class CriterionNode(Node):
    """An outcome of an evaluation, with the generator for its feedback text."""

    KIND: ClassVar[NodeKind | None] = "criterion"
    STYLE: ClassVar[tuple[str, str] | None] = ("[", "]")

    feedback_string_generator: FeedbackStringGenerator = no_feedback

    def copy_into(self, graph: CriteriaGraph) -> CriterionNode:
        return graph.add_criterion_node(self.label, self.summary, self.details, self.feedback_string_generator)

    def check_target(self, target: Node) -> None:
        if target.KIND == "criterion":
            raise CriteriaGraphError(
                f"Both {self.label} and {target.label} are criterion nodes. "
                "Only evaluation nodes can be attached to criterion nodes."
            )


@dataclass(eq=False)
class OutputNode(Node):
    """A terminal node; output nodes have no outgoing edges."""

    KIND: ClassVar[NodeKind | None] = "output"
    STYLE: ClassVar[tuple[str, str] | None] = ("{{", "}}")

    def copy_into(self, graph: CriteriaGraph) -> OutputNode:
        return graph.add_output_node(self.label, self.summary, self.details)


@dataclass(frozen=True, eq=False)
class Edge:
    """A directed edge. Edges compare (and hash) by their endpoints' labels."""

    source: Node
    target: Node

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Edge):
            return NotImplemented
        return (self.source.label, self.target.label) == (other.source.label, other.target.label)

    def __hash__(self) -> int:
        return hash((self.source.label, self.target.label))
