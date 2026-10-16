"""Criteria parser and criteria graphs for Lambda Feedback evaluation functions.

- :func:`build_criteria_parser` parses criteria such as
  ``response = answer where a = 2``.
- :func:`build_quantity_criteria_parser` parses criteria on physical
  quantities, such as ``response matches answer``.
- :class:`CriteriaGraph` links evaluations to the criteria they establish,
  runs them (:meth:`CriteriaGraph.generate_feedback`), turns the criteria
  reached into feedback on a result object such as
  ``lf_toolkit.evaluation.Result`` (:meth:`CriteriaGraph.export_feedback`)
  and renders the graph.
"""

import logging
from importlib.metadata import PackageNotFoundError, version

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
from .quantity_grammar import build_quantity_criteria_parser
from .tree import CriteriaTree

# Library convention: callers decide where log records go (``logging.basicConfig(level=logging.DEBUG)`` shows them).
logging.getLogger(__name__).addHandler(logging.NullHandler())

try:
    __version__ = version("lambdafeedback-criteria")
except PackageNotFoundError:  # running from a source checkout that isn't installed
    __version__ = "0+unknown"

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
    "__version__",
    "build_criteria_parser",
    "build_quantity_criteria_parser",
]
