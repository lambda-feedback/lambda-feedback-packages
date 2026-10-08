"""Trees unrolled from a criteria graph, for display."""

from __future__ import annotations

import json
from collections.abc import Collection
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from .errors import CriteriaGraphError
from .nodes import CriterionNode, EvaluationNode, Node, OutputNode
from .render import CRITERION_STYLE, EVALUATION_STYLE, OUTPUT_STYLE, tree_to_mermaid

if TYPE_CHECKING:
    from .graph import CriteriaGraph

NodeType = Literal["evaluation", "criterion", "main_criterion", "output"]


@dataclass(eq=False)
class CriteriaTree:
    """A node of a tree unrolled from a criteria graph.

    Graph nodes reached a second time become ``RETURN<n>`` output leaves
    ("Go to: <label>"), so the tree stays finite when the graph has cycles.
    """

    label: str
    summary: str
    details: str
    identifier: str
    style: tuple[str, str]
    type_label: NodeType
    parent: CriteriaTree | None = field(default=None, repr=False)
    children: list[CriteriaTree] = field(default_factory=list, repr=False)

    def to_mermaid(self, special_nodes: Collection[str] = ()) -> str:
        """Mermaid flowchart source; nodes labelled in ``special_nodes`` are highlighted."""
        return tree_to_mermaid(self, special_nodes)

    def as_dict(self) -> dict[str, Any]:
        """The subtree as nested dicts with ``label``, ``summary``, ``details``, ``type`` and ``children``."""
        return {
            "label": self.label,
            "summary": self.summary,
            "details": self.details,
            "type": self.type_label,
            "children": [child.as_dict() for child in self.children],
        }

    def to_json(self) -> str:
        """``as_dict()`` as a JSON string."""
        return json.dumps(self.as_dict())


def _tree_node(
    node: Node, identifier: int, main_criteria: Collection[str], parent: CriteriaTree | None = None
) -> CriteriaTree:
    type_label: NodeType
    if isinstance(node, EvaluationNode):
        style, type_label = EVALUATION_STYLE, "evaluation"
    elif isinstance(node, CriterionNode):
        style, type_label = CRITERION_STYLE, "main_criterion" if node.label in main_criteria else "criterion"
    elif isinstance(node, OutputNode):
        style, type_label = OUTPUT_STYLE, "output"
    else:
        raise CriteriaGraphError(f"Cannot display node {node.label} of type {type(node).__name__}.")
    return CriteriaTree(node.label, node.summary, node.details, f"_{identifier}", style, type_label, parent)


def build_tree(graph: CriteriaGraph, starting_evaluation: str, main_criteria: Collection[str] = ()) -> CriteriaTree:
    """Unroll ``graph`` depth-first from the evaluation labelled ``starting_evaluation``."""
    node = graph.evaluations.get(starting_evaluation)
    if node is None:
        raise CriteriaGraphError(f"Unknown evaluation node {starting_evaluation}.")
    root = _tree_node(node, 0, main_criteria)
    identifier = 1
    # Targets are pushed in reverse so that they are popped (and become children) in attachment order.
    stack: list[tuple[Node, CriteriaTree]] = [(edge.target, root) for edge in reversed(node.outgoing)]
    visited = {node.label}
    while stack:
        current, parent = stack.pop()
        if current.label in visited:
            revisit = OutputNode(f"RETURN{identifier}", f"Go to: {current.label}", "Reached a previously visited node.")
            parent.children.append(_tree_node(revisit, identifier, main_criteria, parent))
        else:
            tree_node = _tree_node(current, identifier, main_criteria, parent)
            parent.children.append(tree_node)
            if not isinstance(current, OutputNode):
                visited.add(current.label)
            stack += [(edge.target, tree_node) for edge in reversed(current.outgoing)]
        identifier += 1
    return root
