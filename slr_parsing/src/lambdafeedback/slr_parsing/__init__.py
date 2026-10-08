"""Generic SLR(1) parser engine.

Build a parser from token specifications and productions with
:class:`SLRParser` (or :func:`build_expression_parser` for the common
operand/operator/delimiter shape), then ``parser.parse(parser.scan(text))``.
See :mod:`lambdafeedback.slr_parsing.grammar` for the grammar format.

Extracted from compareExpressions (app/utility/slr_parsing_utilities.py);
depends only on the standard library.
"""

from .actions import (
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
    ErrorAction,
    ErrorCondition,
    ErrorHandler,
    Matcher,
    Production,
    TagHandler,
    TokenProduction,
    TokenSpec,
    catch_undefined,
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

__all__ = [
    "Action",
    "ErrorAction",
    "ErrorCondition",
    "ErrorHandler",
    "ExprNode",
    "GrammarError",
    "Matcher",
    "ParseError",
    "Production",
    "SLRError",
    "SLRParser",
    "ScanError",
    "TagCondition",
    "TagHandler",
    "TagRule",
    "Token",
    "TokenProduction",
    "TokenSpec",
    "TraverseStep",
    "add_tag",
    "append",
    "append_last",
    "build_expression_parser",
    "catch_undefined",
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
