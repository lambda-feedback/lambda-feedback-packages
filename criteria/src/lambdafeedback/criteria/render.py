"""JSON and mermaid renderings of criteria graphs and trees."""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .graph import CriteriaGraph
    from .nodes import Node
    from .tree import CriteriaTree

# Mermaid node shapes (opening, closing).
EVALUATION_STYLE = ("([", "])")
STARTING_EVALUATION_STYLE = (">", "]")
CRITERION_STYLE = ("[", "]")
OUTPUT_STYLE = ("{{", "}}")
SPECIAL_STYLE = ("[[", "]]")


def _text(text: str) -> str:
    """``text`` made safe inside a quoted mermaid label."""
    return text.replace('"', "#quot;")


def _identifier(label: str) -> str:
    """``label`` made safe as (part of) a mermaid node id."""
    return re.sub(r"\W", "_", label)


def graph_to_json(graph: CriteriaGraph) -> str:
    """``graph``'s evaluations, criteria and outputs (summary, details, edge labels) and sufficiencies as JSON."""

    def entry(node: Any, outgoing: bool = True) -> dict[str, Any]:
        data = {
            "summary": node.summary,
            "details": node.details,
            "incoming": [edge.source.label for edge in node.incoming],
        }
        if outgoing:
            data["outgoing"] = [edge.target.label for edge in node.outgoing]
        return data

    return json.dumps(
        {
            "evaluations": {label: entry(node) for label, node in graph.evaluations.items()},
            "criteria": {label: entry(node) for label, node in graph.criteria.items()},
            "outputs": {label: entry(node, outgoing=False) for label, node in graph.outputs.items()},
            "sufficiencies": {
                label: list(sufficiencies)
                for label, sufficiencies in graph.sufficiencies.items()
                if sufficiencies is not None
            },
        }
    )


def graph_to_mermaid(graph: CriteriaGraph) -> str:
    """Mermaid flowchart source for ``graph``; sufficiencies are drawn as dotted edges."""
    node_groups: list[tuple[Mapping[str, Node], tuple[str, str]]] = [
        (graph.evaluations, EVALUATION_STYLE),
        (graph.criteria, CRITERION_STYLE),
        (graph.outputs, OUTPUT_STYLE),
    ]
    keys = {label: f"N_{g}_{i}" for g, (nodes, _) in enumerate(node_groups) for i, label in enumerate(nodes)}
    lines = ["flowchart TD"]
    # Ordered de-duplication (dict keys), so the output doesn't depend on the hash seed.
    edges: dict[tuple[str, str], None] = {}
    sufficiencies: dict[tuple[str, str], None] = {}
    for nodes, (opening, closing) in node_groups:
        for label, node in nodes.items():
            lines.append(f'{keys[label]}{opening}"{_text(label)}<br/>---<br/>{_text(node.details)}"{closing}')
            edges.update(
                dict.fromkeys((keys[e.source.label], keys[e.target.label]) for e in node.outgoing + node.incoming)
            )
            node_sufficiencies = graph.sufficiencies.get(label)
            if node_sufficiencies is not None:
                # A sufficiency naming no node has nothing to point at, so it is not drawn.
                sufficiencies.update(dict.fromkeys((keys[label], keys[s]) for s in node_sufficiencies if s in keys))
    lines += [" --> ".join(edge) for edge in edges]
    lines += [" -.-> ".join(sufficiency) for sufficiency in sufficiencies]
    return "\n\t".join(lines)


def tree_to_mermaid(tree: CriteriaTree, special_nodes: Collection[str] = ()) -> str:
    """Mermaid graph source for ``tree``; nodes labelled in ``special_nodes`` are highlighted."""

    def tree_id(node: CriteriaTree) -> str:
        return f"{_identifier(node.label)}{node.identifier}"

    def edges_from(node: CriteriaTree) -> list[str]:
        return [f"{tree_id(node)} --> {tree_id(child)}" for child in node.children]

    opening, closing = STARTING_EVALUATION_STYLE
    nodes = [f'{tree_id(tree)}{opening}"{_text(tree.summary)}"{closing}']
    edges = edges_from(tree)
    stack = list(tree.children)
    while stack:
        child = stack.pop()
        opening, closing = SPECIAL_STYLE if child.label in special_nodes else child.style
        nodes.append(f'{tree_id(child)}{opening}"{_text(child.summary)}"{closing}')
        edges += edges_from(child)
        stack += child.children
    return "\n\t".join(["graph TD", *nodes, *edges])
