"""Generic SLR(1) parser engine.

Build a parser from token specifications and productions with
:class:`SLRParser` (or :func:`build_expression_parser` for the common
operand/operator/delimiter shape), then ``parser.parse(parser.scan(text))``.
See :mod:`lambdafeedback.slr_parsing.grammar` for the grammar format.

Extracted from compareExpressions (app/utility/slr_parsing_utilities.py);
depends only on the standard library.
"""

import logging
from importlib.metadata import PackageNotFoundError, version

from .actions import (
    END_DELIMITER_LABEL,
    GROUP_LABEL,
    START_DELIMITER_LABEL,
    append,
    append_last,
    compose,
    create_node,
    flatten,
    group,
    infix,
    insert_infix,
    join,
    operate,
    proceed,
    relabel,
)
from .builder import build_expression_parser
from .errors import GrammarError, ParseError, ScanError, SLRError, new_root_on_error
from .grammar import (
    Action,
    CatchAll,
    ErrorAction,
    ErrorCondition,
    ErrorHandler,
    GrammarSymbol,
    Lexeme,
    Matcher,
    ParseState,
    Production,
    TagHandler,
    TokenMatcher,
    TokenPattern,
    TokenProduction,
    TokenSpec,
)
from .parser import SLRParser
from .tags import (
    TagCondition,
    TagRule,
    add_tag,
    inherit_tags,
    intersection_rule,
    remove_tag,
    replace_tag,
    union_rule,
)
from .tokens import (
    ExprNode,
    Token,
    TraverseStep,
    traverse_group,
    traverse_infix,
    traverse_postfix,
    traverse_prefix,
)

# Library convention: callers decide where log records go (``logging.basicConfig(level=logging.DEBUG)`` shows them).
logging.getLogger(__name__).addHandler(logging.NullHandler())

try:
    __version__ = version("lambdafeedback-slr-parsing")
except PackageNotFoundError:  # running from a source checkout that isn't installed
    __version__ = "0+unknown"

__all__ = [
    "END_DELIMITER_LABEL",
    "GROUP_LABEL",
    "START_DELIMITER_LABEL",
    "Action",
    "CatchAll",
    "ErrorAction",
    "ErrorCondition",
    "ErrorHandler",
    "ExprNode",
    "GrammarError",
    "GrammarSymbol",
    "Lexeme",
    "Matcher",
    "ParseError",
    "ParseState",
    "Production",
    "SLRError",
    "SLRParser",
    "ScanError",
    "TagCondition",
    "TagHandler",
    "TagRule",
    "Token",
    "TokenMatcher",
    "TokenPattern",
    "TokenProduction",
    "TokenSpec",
    "TraverseStep",
    "__version__",
    "add_tag",
    "append",
    "append_last",
    "build_expression_parser",
    "compose",
    "create_node",
    "flatten",
    "group",
    "infix",
    "inherit_tags",
    "insert_infix",
    "intersection_rule",
    "join",
    "new_root_on_error",
    "operate",
    "proceed",
    "relabel",
    "remove_tag",
    "replace_tag",
    "traverse_group",
    "traverse_infix",
    "traverse_postfix",
    "traverse_prefix",
    "union_rule",
]
