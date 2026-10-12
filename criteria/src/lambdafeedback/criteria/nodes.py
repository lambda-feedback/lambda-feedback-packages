"""Nodes and edges of a criteria graph.

A criteria graph alternates between *evaluation* nodes, which run a check and
report which criteria hold, and *criterion* nodes, which record an outcome
and lead to further evaluations or to *output* nodes.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeAlias

ReachedCriteria: TypeAlias = Mapping[str, Mapping[str, Any] | None]
"""``{criterion_label: feedback_inputs_or_None}`` for the criteria that hold (or were reached)."""

Evaluate: TypeAlias = Callable[[Any], ReachedCriteria]
"""``evaluate(response) -> {criterion_label: feedback_inputs_or_None}`` for the criteria that hold."""

FeedbackStringGenerator: TypeAlias = Callable[[Mapping[str, Any]], str | None]
"""Renders a criterion's feedback text from the inputs its evaluation reported."""


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
    """A graph node. Nodes compare (and hash) by identity; within a graph, labels are unique."""

    label: str
    summary: str
    details: str
    incoming: list[Edge] = field(default_factory=list, init=False, repr=False)
    outgoing: list[Edge] = field(default_factory=list, init=False, repr=False)


@dataclass(eq=False)
class EvaluationNode(Node):
    """Runs ``evaluate`` on the response; the criteria it reports lead onwards.

    Setting ``replacement`` (e.g. to ``CriteriaGraph.END``) disables the
    evaluation: feedback generation goes to the replacement instead.
    ``sufficiencies`` lists criteria whose evaluations can stand in for this
    one when choosing where to start (``None``: it can't be stood in for;
    see ``CriteriaGraph.starting_evaluations``).
    """

    evaluate: Evaluate | None = None
    replacement: Node | None = None
    sufficiencies: list[str] | None = None


@dataclass(eq=False)
class CriterionNode(Node):
    """An outcome of an evaluation, with the generator for its feedback text."""

    feedback_string_generator: FeedbackStringGenerator = no_feedback


@dataclass(eq=False)
class OutputNode(Node):
    """A terminal node; output nodes have no outgoing edges."""


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
