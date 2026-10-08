# Phase 1: `lambdafeedback.slr_parsing`: done

No dependencies. The single `parser.py` (845 lines) is now 7 modules. Released as `0.2.0`; see [`slr_parsing/CHANGELOG.md`](../../slr_parsing/CHANGELOG.md) for the migration table.

## Target modules

| Module | Contents |
|---|---|
| `tokens.py` | `Token`, `ExprNode`, traversal steps |
| `actions.py` | Reduction actions (`proceed`, `append`, `append_last`, `join`, `create_node`, `relabel`, `group`, `operate`, `infix`, `insert_infix`, `compose`, `flatten`) |
| `tags.py` | `add_tag`, `remove_tag`, `replace_tag`, `inherit_tags`, `union_rule`, `intersection_rule` |
| `grammar.py` | Documented grammar format; `Production`, `ErrorHandler` named tuples; type aliases; `catch_undefined` |
| `parser.py` | `SLRParser`, with `__init__` split into `_prepare_scanner`, `_check_duplicate_productions`, `_tokenise_productions`, `_classify_symbols`, `_compute_first`, `_compute_follow`, `_build_states`, `_build_table`/`_resolve`, `_report_unreachable` |
| `builder.py` | `build_expression_parser` |
| `errors.py` | `SLRError` → `GrammarError`, `ScanError`, `ParseError` (with `details()`), plus `new_root_on_error` |

**Deviation:** there is no `TokenRule` named tuple. Token specifications distinguish 2-tuples (literal patterns) from 3-tuples (matcher / catch-all / grammar-only) by length, so a `TokenRule(pattern, label, matcher=None)` would be ambiguous. The three shapes are documented in `grammar.py` and typed as `TokenSpec` instead.

## Checklist

### Bugs (regression test, one commit each)

- [x] `ExprNode(tags=set())` mutable default shared by all nodes; `copy()` shared the set; **also found:** `tag_transfer` returned a single child's own set as the parent's tags.
- [x] Custom `expression_node` became a literal token regex, so `2E`/`xE` failed to parse. 6 parity probes now parse.
- [x] `parse()` crashed on tokens left after ACCEPT; `new_root_on_error` also dropped the offending token.
- [x] `SLRParser` sorted the caller's `token_list` in place.
- [x] `scan()` with an unknown mode raised `UnboundLocalError`.
- [x] `ExprNode.__str__` hid a single tag. The empty-tags spacing changed in 28 criteria parity probes (cosmetic).
- [x] `operate(0)` accepted (and would consume the whole output stack).
- [x] `package()` stored the list repr of its children, and `discard_output_until_on_error` could never work: **both removed**, since neither was used.
- [ ] ~~`group(empty=True)` swapped delimiter labels~~: not observable (only the contents are used); fixed as part of the tidy-up.
- [x] **Found during the refactor:** reductions keyed by production body (productions sharing a body ran the last one's action).
- [x] **Found during the refactor:** infix productions built from `op[0]`, the first character of the operator, which broke multi-character operators.
- [x] **Found during the refactor:** `traverse_group` called the action twice per group, which duplicated units' `REVERTED_UNIT` messages (6 parity probes deduplicated).
- [x] **Found during the refactor:** `parse([])` raised `IndexError`; it now raises `ParseError("Unexpected end of input.")`.
- [x] **Pre-release review:** `new_root_on_error` looped forever when the error was in state 0 or at the end of input; it now raises `ParseError`.
- [x] **Pre-release review:** each recovered root added a level of recursion (`RecursionError` at ~1000 roots); `parse()` now loops.
- [x] **Pre-release review:** malformed grammars failed late or silently: undeclared body symbols became catch-all symbols, empty bodies crashed at parse time, multi-symbol heads used their first symbol, and undeclared start/end/null raised `ScanError`. All are now `GrammarError`s at construction.
- [x] **Pre-release review:** `ExprNode` inherited `Token`'s label-only equality; nodes now compare by identity.

### Release

- [x] MIT `LICENSE`, `README.md` (PyPI long description), project metadata (readme, license, authors, classifiers, URLs).

### Restructure

- [x] Split into the modules above (verbatim move first, then the tidy-up).
- [x] Named table-building steps. The parse tables were verified **identical** to the previous code for all 12 grammars in the repo (criteria; both conventions; units strict/natural × 4 unit sets; a builder grammar).
- [x] Scanner partitions and regexes compiled once; `closure()` memoised. Construction was already only a few ms per grammar, so the real performance win is caching parsers in consumers (Phases 3–4).
- [x] Dead code removed (`break` after `raise`, duplicate assignments, `state_string_list`, unused `group_node`).
- [x] `logging` instead of `print`/`verbose`.
- [x] Exception hierarchy.
- [x] Documented `Token` label-only equality.

### API

- [x] Renames recorded in `CHANGELOG.md` (`SLRParser`, `build_expression_parser`, `custom_*`, tag helpers).
- [x] Mutable defaults → tuples/`None`.
- [x] `default_error_action` → `SLRParser._parse_error`.

### Types & lint

- [x] Full type hints; strict mypy flags (spelled out per module, since `strict` is global-only).
- [x] ruff lint and format.

### Tests added (22 → 45)

- [x] `test_regressions.py`: one test per bug above.
- [x] `test_engine.py`: FIRST/FOLLOW and state count on the textbook grammar, precedence and associativity, scanner (longest match, matchers, catch-all, `ScanError`), `ParseError` messages and `details()`, error-handler dispatch and state items, debug tracing via logging.
