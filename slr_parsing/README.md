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

From git (not on PyPI yet):

```bash
pip install "lambdafeedback-slr-parsing @ git+https://github.com/lambda-feedback/lambda-feedback-packages.git@v0.3.0-rc.1#subdirectory=slr_parsing"
```

Requires Python 3.12+. The import root is `lambdafeedback.slr_parsing`.

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

**Precedence:** later entries in `infix_operators` bind tighter, so list
`+` before `*`. Every operator is left-associative (`a-b-c` is `(a-b)-c`),
including `^`, so a right-associative power needs a custom production. Spaces
around operators and delimiters are kept in their tokens' content, so
`content_string()` reproduces the input.

## Writing a grammar

For full control, pass token specifications and productions to `SLRParser`.
A `TokenPattern` scans its pattern from input, a `TokenMatcher` scans with a
function, a `CatchAll` collects text nothing else matches, and a
`GrammarSymbol` (a nonterminal) only appears in productions. Every grammar
symbol is declared this way, because production strings are scanned with the
same specifications. Each production is `(head, body, action)`; the action builds
the output tree when the production is reduced. When productions conflict,
the one listed later wins. Productions headed by the start symbol are never
reduced (reaching their end accepts the input), so their action is never
called and can be `None`.

A token's pattern is a literal string, or a `Lexeme`: the first of several
literal forms, optionally with spaces around it (`Lexeme(("+", "-"), True,
True)` matches ` + `). Anything else, such as a run of digits, is scanned by a
matcher function.

```python
from itertools import takewhile

from lambdafeedback.slr_parsing import (
    GrammarSymbol,
    Lexeme,
    SLRParser,
    TokenMatcher,
    TokenPattern,
    create_node,
    group,
    infix,
    proceed,
)


def number(text):
    digits = "".join(takewhile(str.isdigit, text))
    return (digits, int(digits)) if digits else (None, None)


tokens = [
    TokenPattern("START", "START"),
    TokenPattern("END", "END"),
    TokenPattern("NULL", "NULL"),
    GrammarSymbol("E", "E"),
    GrammarSymbol("T", "T"),
    GrammarSymbol("F", "F"),
    TokenPattern(Lexeme(("+",), space_before=True, space_after=True), "PLUS"),
    TokenPattern(Lexeme(("*",), space_before=True, space_after=True), "TIMES"),
    TokenPattern("(", "LPAR"),
    TokenPattern(")", "RPAR"),
    TokenMatcher("n", "NUM", number),  # in productions "n"; in input, whatever `number` matches
]
productions = [
    ("START", "E", None),  # start productions accept; their action never runs
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
| `GrammarError` | the grammar is invalid (malformed production or error handler, undeclared symbol, empty body, duplicate production, missing action, ...) |
| `ScanError` | the input contains text no token matches (and the grammar has no catch-all) |
| `ParseError` | the input does not match the grammar; the message is one line, and `details()` gives the full parser state |

`error_handlers=[(condition, action), ...]` customises what happens at syntax
errors. `action(parser, state)` changes the `ParseState` so that parsing can
continue, or raises (`parser.parse_error(state)` builds the usual
`ParseError`). `new_root_on_error` finishes the current tree and parses the
rest of the input as further roots.

## Tags

`tag_handler` (default `inherit_tags`, the union of the children's tags)
computes each new node's `tags` set. `add_tag`, `remove_tag` and
`replace_tag` modify them.

Only actions that build a new node (`create_node`, `group`, `operate`,
`infix`, `insert_infix`) run the tag handler. Actions that change an existing
node in place (`append`, `append_last`, `join`, `relabel`, `flatten`) leave
its tags unchanged.

## Equality

`Token`s compare and hash by **label only**, because the parser uses them as
grammar symbols. `ExprNode`s compare by **identity**: compare trees by their
content (for example with `content_string()`), not with `==`.

## Debugging

Set the `lambdafeedback.slr_parsing.parser` logger to `DEBUG` to trace every
shift and reduction. `parser.parsing_table_to_string()` and
`parser.state_string(state)` print the generated table and states.

## Changelog

See [CHANGELOG.md](https://github.com/lambda-feedback/lambda-feedback-packages/blob/main/slr_parsing/CHANGELOG.md).

## License

MIT
