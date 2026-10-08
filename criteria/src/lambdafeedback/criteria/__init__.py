"""Criteria parser and criteria graphs for Lambda Feedback evaluation functions.

- :func:`build_criteria_parser` parses criteria such as
  ``response = answer where a = 2``.
- :class:`CriteriaGraph` links evaluations to the criteria they establish,
  runs them (:meth:`CriteriaGraph.generate_feedback`), turns the criteria
  reached into feedback on a result object such as
  ``lf_toolkit.evaluation.Result`` (:meth:`CriteriaGraph.export_feedback`)
  and renders the graph.
"""

from .errors import CriteriaError, CriteriaEvaluationError, CriteriaGraphError
from .grammar import build_criteria_parser
from .graph import CriteriaGraph
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
)
from .tree import CriteriaTree

__all__ = [
    "CriteriaError",
    "CriteriaEvaluationError",
    "CriteriaGraph",
    "CriteriaGraphError",
    "CriteriaTree",
    "CriterionNode",
    "Edge",
    "Evaluate",
    "EvaluationNode",
    "FeedbackStringGenerator",
    "Node",
    "OutputNode",
    "ReachedCriteria",
    "ResultLike",
    "build_criteria_parser",
]
