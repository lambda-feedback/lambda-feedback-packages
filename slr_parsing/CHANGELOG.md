# Changelog: lambdafeedback-slr-parsing

## 0.2.0 (unreleased)

The first release after the extraction refactor. The import path is now `lambdafeedback.slr_parsing` (was `slr_parsing`).

### Renamed

| v0.1 | 0.2.0 |
|---|---|
| `slr_parsing` (import) | `lambdafeedback.slr_parsing` |
| `SLR_Parser` | `SLRParser` |
| `SLR_expression_parser(..., costum_tokens=, costum_productions=)` | `build_expression_parser(..., custom_tokens=, custom_productions=)` |
| `tag` | `add_tag` |
| `tag_removal` | `remove_tag` |
| `tag_replace` | `replace_tag` |
| `tag_transfer` | `inherit_tags` |
| `tag_rule_union` / `tag_rule_intersection` | `union_rule` / `intersection_rule` |

### Changed

- **Errors:** bare `Exception`s are replaced by `GrammarError` (invalid grammar), `ScanError` (text no token matches) and `ParseError` (input doesn't match the grammar). All derive from `SLRError` and `ValueError`. `ParseError`'s message is a one-line summary ("Unexpected end of input.", "Unexpected OP '+' at position 3."); the full parser-state dump that used to be the message is available from `ParseError.details()`, with the parts as attributes. An invalid `ExprNode` child raises `TypeError`.
- **Logging instead of printing:** `parse()` no longer takes `verbose`; set the `lambdafeedback.slr_parsing.parser` logger to DEBUG to trace shifts and reductions. Unreachable grammar states and reductions are logged as a WARNING instead of printed, and the start state is no longer falsely reported.
- `build_expression_parser` drops the unused `group_node` parameter; sequence defaults are tuples instead of shared mutable lists.
- `SLRParser` keeps its construction internals private. The public surface is `scan`, `parse`, `parsing_action`, `parsing_table`, `states` (now a list of kernel item tuples, was a dict of kernel → closure), `productions`, `token_list`, `start_token`/`end_token`/`null_token`, `error_handler`, `tag_handler` and the debug helpers `state_string` and `parsing_table_to_string`. `state_string_list` is removed.
- Error handlers are normalised to `ErrorHandler(condition, action)` named tuples; plain 2-tuples are still accepted.
- `replace_tag(node, t, t)` keeps the tag (it used to remove it).
- **`ExprNode` equality is by identity.** Nodes used to inherit `Token`'s label-only equality, so any two trees with the same root label compared equal (`x+x == x+(x+x)`). `Token`s still compare by label, and a `Token` never equals an `ExprNode`. Compare trees by content (e.g. `content_string()`) instead.
- **Stricter grammar checks:** `SLRParser` raises `GrammarError` for:
  - a production body containing text that is not a declared symbol (with a catch-all token it used to become a catch-all symbol silently);
  - an empty body (ε-productions were never supported and crashed while parsing);
  - a head that isn't exactly one symbol (only the first symbol was used);
  - an undeclared start, end or null symbol (was `ScanError`);
  - a production that isn't a `(head, body, action-or-None)` triple (a 2-tuple raised `IndexError`; a non-callable action raised `TypeError` on the first parse);
  - an error handler that isn't a `(condition, action)` pair of callables (was `TypeError`).
- **Token patterns are literals, not regular expressions.** The pattern of a `(pattern, label)` token specification is a plain string, matched exactly, or the new `Lexeme(forms, space_before=False, space_after=False)`: the first of several literal forms, optionally with spaces around it, where a space inside a form matches one or more spaces. `(r" *\+ *", "PLUS")` becomes `(Lexeme(("+",), True, True), "PLUS")`, and `(r"\(", "LPAR")` becomes `("(", "LPAR")`. Anything else (a run of digits, say) is scanned with a matcher, the `(symbol, label, matcher)` shape, which was already supported. Ties between equally long matches go to the specification with the larger `Lexeme.weight` (the longest form, plus 2 per side allowing spaces) or the longer literal, mirroring the old order by pattern length. `build_expression_parser` builds `Lexeme`s for its operators and delimiters, so its callers are unaffected.
- `repr(ExprNode)` matches `str(ExprNode)`.
- Modules: `tokens`, `actions`, `tags`, `grammar` (with the grammar format documented), `errors`, `parser`, `builder`. Fully type-annotated (`py.typed`). The type aliases used in public signatures (`ErrorCondition`, `ErrorAction`, `TraverseStep`, `TagRule`, `TagCondition`) are exported from the package root.

### Fixed

- `ExprNode` tag sets are no longer shared. Before, every node built without a tag handler shared the mutable default `tags=set()`, `copy()` shared the original's set, and `tag_transfer` returned a single child's own set as its parent's tags. Tagging one node could tag unrelated nodes.
- `str(ExprNode)` shows the node's tags whenever it has any; it used to hide them unless there were two or more. Empty tags print as `tags: {}` (was `tags:  {}`).
- A custom `expression_node` passed to the expression-parser builder no longer becomes a literal token. The implicit-multiplication convention parser in `expression_parsing` uses `"E"` as its node symbol, so every capital `E` in an input was scanned as a grammar symbol and inputs such as `2E` or `xE` failed to parse.
- Multi-character infix operators (such as `**`) work in the expression-parser builder. Its productions were built from only the first character of each operator symbol.
- `SLR_Parser` no longer sorts the caller's `token_list` in place.
- `scan()` raises `ValueError` for an unknown `mode` (it used to crash with `UnboundLocalError`), and matches the mode exactly rather than by substring.
- `group(0)` and `operate(0)` raise `ValueError`. `operate(0)` was accepted and would have consumed the entire output stack.
- Each production runs its own reduction action. Actions used to be looked up by production *body*, so two productions with the same body but different heads (such as `A -> x` and `B -> x`) both ran whichever action was defined last. None of the grammars in these packages had such a pair.
- Traversing a `GROUP` node calls the action once, not twice. Actions with side effects ran twice per group: units recorded every reverted unit group as two identical `REVERTED_UNIT` messages.
- `new_root_on_error` works: parsing resumes at the offending token and the extra roots are appended to the output. Before, the offending token was dropped and `parse()` crashed on the remaining tokens. When no root can be finished (empty input, a bad first token, or an error at the end of input), it raises `ParseError` instead of looping forever.
- Recovered roots are parsed in a loop rather than recursively, so inputs with many roots no longer hit `RecursionError`.
- `append`, `append_last` and `join` work on one-symbol production bodies; they used to raise `IndexError` (their slices selected the whole output stack). `append_last` no longer makes a node its own child there.
- `build_expression_parser(nodes=...)` works with regex patterns such as `[0-9]+`. Its productions used each node's pattern text as a grammar symbol, so only patterns that matched themselves (such as `pi`) worked; operands are now referred to by label.
- `build_expression_parser` with several delimiter pairs adds one delimiter production instead of one per pair. All pairs scan to the same symbols, so every production but the last was unreachable, and each construction logged an "unreachable reductions" warning. Parse results are unchanged (the last pair's action was already the one used).
- `relabel` keeps a tree node's children and tags. It used to replace the node with a plain `Token`, discarding its subtree. Only start productions used it, and those are never reduced, so no grammar here was affected.
- `ExprNode.copy()` and `tree_string()` are iterative, so deeply nested input (such as a thousand nested brackets) no longer raises `RecursionError`. The parser and `traverse` already were.

### Removed

- `package` reduction action: unused, and it stored the `repr` of its children list as the node content. Use `join` (merge into one node) or a custom action.
- `discard_output_until_on_error`: unused, and it could not work. It popped parser output without unwinding the state stack, so every use ended in `IndexError`.
