# Phase 2: `lambdafeedback.criteria`, and retiring `evaluation_result`: done

Depends on `slr_parsing`. Version `0.2.0` (unreleased); see [`criteria/CHANGELOG.md`](../../criteria/CHANGELOG.md) for the migration tables (including `EvaluationResult` → `lf_toolkit.evaluation.Result`).

## Modules

| Module | Contents |
|---|---|
| `grammar.py` (was `parsing.py`) | `TOKENS` / `PRODUCTIONS` as immutable tuples; `build_criteria_parser(reserved_expressions)` |
| `nodes.py` | `Node`, `EvaluationNode`, `CriterionNode`, `OutputNode` (dataclasses), `Edge`; `ReachedCriteria`, `ResultLike` |
| `graph.py` | `CriteriaGraph`, including the feedback methods `resolve_feedback`, `export_feedback` (override to export differently) and `test_data` |
| `tree.py` | `CriteriaTree`, `build_tree` |
| `render.py` | JSON and mermaid renderings, style constants |
| `errors.py` | `CriteriaError` → `CriteriaGraphError`, `CriteriaEvaluationError` |

**Deviations from the plan:**
- **lf_toolkit is not a runtime dependency.** lf_toolkit@ae52fa6 declares its dev tools as runtime requirements (80 packages / 237 MB), so `CriteriaGraph.export_feedback` types against a `ResultLike` protocol. lf_toolkit is a dev-only dependency, and `test_feedback.py` checks compatibility with the real `Result`. Upstream fixes are drafted in [upstream-lf-toolkit.md](upstream-lf-toolkit.md).
- **Blank feedback** (decided in Phase 2): `export_feedback` records every reached tag, adding `""` for `None`/blank feedback, which keeps the tags compareExpressions' tests rely on. The resulting empty `<br>` segments in lf_toolkit's `Result.feedback` are the subject of the upstream fix.
- **`CriteriaGraph.END` is kept.** The plan listed it as unused, but compareExpressions uses it (`graph.add_node(CriteriaGraph.END)`, `evaluation.replacement = CriteriaGraph.END`). `RETURN` was the unused one. *(Pre-release review: the shared node is replaced by `graph.add_end_node()` and `replacement = CriteriaGraph.END_LABEL`; compareExpressions needs those two one-line changes.)*
- **Productions are kept as an explicit list** rather than generated from an `OTHER`/`RESERVED` product: 26 literal lines are clearer than the generator, and they make the precedence order obvious.

## Checklist

### Bugs (regression test, one commit each)

- [x] `Tree.mermaid()` emptied the tree it rendered.
- [x] `generate_criteria_parser()` appended reserved words to the module-level default token list, which leaked them into every later parser.
- [x] `build_tree("unknown")` raised `AttributeError`.
- [x] `add_node(Evaluation)` always raised; it also dropped `evaluate`, and **(also found)** a criterion's `feedback_string_generator`.
- [x] Nodes unhashable; comparison with non-nodes crashed.
- [x] `generate_feedback` printed graph internals on failure → `CriteriaEvaluationError`.
- [x] **Found during the refactor:** feedback order and mermaid output depended on the hash seed (set iteration). Checked across 4 seeds in a subprocess test.
- [x] **Found during the refactor:** `starting_evaluations` looped forever on cyclic sufficiencies.

### Retire `evaluation_result`

- [x] Feedback helpers (now `CriteriaGraph` methods), tested against a recording fake and the real lf_toolkit `Result`.
- [x] Package deleted; removed from the dev env, the test runner, the configs and the README.
- [x] Migration notes in `criteria/CHANGELOG.md`, including the behaviour differences (blank feedback, `tags` only in test data, stripping).

### Restructure / API / types

- [x] Nested classes → module-level dataclasses; `CriteriaTree` with `children`/`parent`.
- [x] Renamed: `build_criteria_parser`, `to_json`/`to_mermaid`, `as_dict`; removed the unused `entry_evaluations`, `RETURN`, `results`/`consequences` aliases and node `tags`.
- [x] The `__main__` demo is gone (its criteria strings are covered by the parity probes).
- [x] Graph JSON, mermaid, tree JSON/mermaid, feedback and starting evaluations verified **identical** to the pre-restructure code on a graph with a cycle and sufficiencies.
- [x] Strict mypy flags; ruff lint and format.

### Pre-release review

Changes after the restructure, so they intentionally differ from the pre-restructure output noted above (all listed in the CHANGELOG):

- [x] `add_*_node` signatures cleaned up; `attach` dispatches explicitly and rejects keywords for the other node kind, or any node keywords for an existing target.
- [x] Labels unique across node kinds; unknown criteria, sufficiencies, tags and non-mapping `evaluate` results raise `CriteriaGraphError` instead of `KeyError`/`ValueError`.
- [x] Mermaid: sufficiency edges link the real nodes, quotes are escaped, tree ids are safe and unique. Tree children, and the tree mermaid's node declarations, in attachment order.
- [x] `starting_evaluations` / `generate_feedback` / `trees` take a criterion label only (resolved the TODO).
- [x] Replacement chains are followed (with cycle protection).

### Publishing

- [x] MIT `LICENSE`, `README.md` (PyPI long description), project metadata (readme, license, authors, classifiers, URLs).

### Tests (10 → 64)

- [x] `test_regressions.py`, `test_feedback.py`, and `test_graph.py` (attach rules and errors, sufficiencies, replacement, breadth-first feedback, trees with RETURN leaves, renderings).
