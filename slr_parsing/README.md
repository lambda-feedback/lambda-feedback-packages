# lambdafeedback-slr-parsing

A small, dependency-free SLR(1) parser generator for
[Lambda Feedback](https://github.com/lambda-feedback) evaluation functions.
You describe a grammar as token specifications and productions, and get a
scanner and a parser that build an expression tree (`ExprNode`) with
per-node tags. The criteria DSL, the expression conventions and the
physical-quantity parser in the other `lambdafeedback-*` packages are all
built on it.

Originally extracted from the
[compareExpressions](https://github.com/lambda-feedback/compareExpressions)
evaluation function.

## Install

```bash
pip install lambdafeedback-slr-parsing
```

Requires Python 3.11+. The import root is `lambdafeedback.slr_parsing`.

## Quick start: operator expressions

`build_expression_parser` covers the common shape of operands, infix operators
and delimiters. Text that no token matches becomes an `UNDEFINED` operand.

```python
from lambdafeedback.slr_parsing import build_expression_parser, group

parser = build_expression_parser(
    infix_operators=[("+", "ADD"), ("*", "MUL")],
    delimiters=[(("(", ")"), group(1))],
)
(root,) = parser.parse(parser.scan("2*(x+1)"))
print(root.tree_string())
# MUL: * tags: {}
# 0: UNDEFINED: 2 tags: {}
# 1: GROUP: ['(', ')'] tags: {}
#     0: ADD: + tags: {}
#         0: UNDEFINED: x tags: {}
#         1: UNDEFINED: 1 tags: {}
root.content_string()  # '2*(x+1)'
```

## Writing a grammar

For full control, pass token specifications and productions to `SLRParser`.
Grammar symbols (`START`, `END`, `NULL` and the nonterminals) are declared as
tokens too, because production strings are scanned with the same
specifications. Each production is `(head, body, action)`; the action builds
the output tree when the production is reduced. When productions conflict,
the one listed later wins.

```python
import re

from lambdafeedback.slr_parsing import SLRParser, create_node, group, infix, proceed


def number(text):
    match = re.match(r"[0-9]+", text)
    return (match.group(), int(match.group())) if match else (None, None)


tokens = [
    ("START", "START"),
    ("END", "END"),
    ("NULL", "NULL"),
    ("E", "E"),
    ("T", "T"),
    ("F", "F"),
    (r"\+", "PLUS"),
    (r"\*", "TIMES"),
    (r"\(", "LPAR"),
    (r"\)", "RPAR"),
    ("n", "NUM", number),  # in productions "n"; in input, whatever `number` matches
]
productions = [
    ("START", "E", proceed),
    ("E", "E+T", infix),
    ("E", "T", proceed),
    ("T", "T*F", infix),
    ("T", "F", proceed),
    ("F", "(E)", group(1)),
    ("F", "n", create_node),
]
parser = SLRParser(tokens, productions, "START", "END", "NULL")
(root,) = parser.parse(parser.scan("1+2*3"))
```

`lambdafeedback.slr_parsing.grammar` documents the four token-specification
shapes. `lambdafeedback.slr_parsing.actions` lists the built-in reduction
actions (`create_node`, `infix`, `group`, `operate`, `join`, `compose`, ...).

ε-productions (empty bodies) are not supported.

## Errors

All exceptions derive from `SLRError` and `ValueError`:

| Exception | Raised when |
|---|---|
| `GrammarError` | the grammar is invalid (undeclared symbol, empty body, duplicate production, missing action, ...) |
| `ScanError` | the input contains text no token matches (and the grammar has no catch-all) |
| `ParseError` | the input does not match the grammar; the message is one line, and `details()` gives the full parser state |

`error_handler=[(condition, action), ...]` customises what happens at syntax
errors. `new_root_on_error` finishes the current tree and parses the rest of
the input as further roots.

## Tags

`tag_handler` (default `inherit_tags`, the union of the children's tags)
computes each new node's `tags` set. `add_tag`, `remove_tag` and
`replace_tag` modify them.

## Equality

`Token`s compare and hash by **label only**, because the parser uses them as
grammar symbols. `ExprNode`s compare by **identity**: compare trees by their
content (for example with `content_string()`), not with `==`.

## Debugging

Set the `lambdafeedback.slr_parsing.parser` logger to `DEBUG` to trace every
shift and reduction. `parser.parsing_table_to_string()` and
`parser.state_string(state)` print the generated table and states.

## Changelog

See [CHANGELOG.md](https://github.com/m-messer/lambda-feedback-packages/blob/main/slr_parsing/CHANGELOG.md).

## License

MIT
