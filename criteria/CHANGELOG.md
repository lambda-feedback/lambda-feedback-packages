# Changelog: lambdafeedback-criteria

## 0.2.0 (unreleased)

The first release after the extraction refactor. The import path is now `lambdafeedback.criteria` (was `criteria`).

### Renamed and restructured

| v0.1 | 0.2.0 |
|---|---|
| `criteria` (import) | `lambdafeedback.criteria` |
| `generate_criteria_parser(reserved, token_list=, productions=)` | `build_criteria_parser(reserved, token_list=, productions=)`; the defaults are the tuples `grammar.TOKENS` / `grammar.PRODUCTIONS` |
| `criteria.parsing.base_token_list` / `base_productions` | `criteria.grammar.TOKENS` / `PRODUCTIONS` |
| `CriteriaGraph.Evaluation` / `.Criterion` / `.Output` / `.Edge` / `.Node` | `EvaluationNode` / `CriterionNode` / `OutputNode` / `Edge` / `Node` (module-level dataclasses) |
| `CriteriaGraph.Tree` | `CriteriaTree`, with `children` / `parent` instead of `outgoing` / `incoming` |
| `graph.json()` / `graph.mermaid()` | `graph.to_json()` / `graph.to_mermaid()` |
| `tree.json()` / `tree.mermaid(special_nodes)` / `tree.as_dictionary()` | `tree.to_json()` / `tree.to_mermaid(special_nodes)` / `tree.as_dict()` |
| `graph.build_tree(start, return_node=..., main_criteria=None)` | `graph.build_tree(start, main_criteria=())` |
| `graph.starting_evaluations(label)` returned a `set` | returns an ordered `list` |

`CriteriaGraph.END`, the graph-building methods (`add_evaluation_node`, `add_criterion_node`, `add_output_node`, `add_node`, `attach`, `add_sufficiencies`), `generate_feedback`, `trees`, and node attributes (`label`, `summary`, `details`, `incoming`, `outgoing`, `evaluate`, `replacement`, `feedback_string_generator`) keep their names.

Removed (unused): `CriteriaGraph(identifier, entry_evaluations=)` (never read), `CriteriaGraph.RETURN`, the `Evaluation.results` / `Criterion.consequences` aliases of `outgoing`, and the node `tags` attributes.

Signatures: `add_evaluation_node` no longer accepts `feedback_string_generator`, and `add_criterion_node` no longer accepts `sufficiencies` / `evaluate` (they only existed to serve `attach`). `attach` still takes all three and now raises `CriteriaGraphError` when one doesn't apply to the kind of node it creates; previously `evaluate` for a new criterion was silently ignored.

Errors: graph misuse raises `CriteriaGraphError` (a `ValueError`) instead of bare `Exception`; `CriteriaError` is the common base.

Modules: `grammar` (was `parsing`), `nodes`, `graph`, `tree`, `render`, `errors`. Fully type-annotated (`py.typed`).

### Replaces `compareexpressions-evaluation-result`

The `evaluation_result` package is retired. Use `lf_toolkit.evaluation.Result` from [toolkit-python](https://github.com/lambda-feedback/toolkit-python) together with the new `CriteriaGraph` feedback methods: `resolve_feedback(reached, custom_feedback)` gives the `(tag, text)` pairs, `export_feedback(result, reached, custom_feedback)` adds them to a result, and the staticmethod `CriteriaGraph.test_data(graphs)` builds the test-data payload. `export_feedback` types against a `ResultLike` protocol (`tags` + `add_feedback(tag, text)`), so this package doesn't depend on lf_toolkit. To export feedback somewhere else, subclass `CriteriaGraph` and override `export_feedback`.

| `EvaluationResult` (v0.1) | Replacement |
|---|---|
| `EvaluationResult()` | `lf_toolkit.evaluation.Result()` |
| `result.add_feedback((tag, text))` | `result.add_feedback(tag, text)` |
| `result.add_feedback_from_tags(tags, graph, custom_feedback)` | `graph.export_feedback(result, tags, custom_feedback)` |
| `result.add_criteria_graph(name, graph)` + `serialise(include_test_data=True)` | `{**result.to_dict(include_test_data=True), **CriteriaGraph.test_data({name: graph, ...})}` |
| `result.serialise()` / `result[key]` | `result.to_dict()` |
| `result.get_tags()` | `result.tags` |
| `result.get_feedback(tag)` (returned indices) | `result.get_feedback(tag)` (returns the texts) |
| `result.latex` / `result.simplified` | `Result(latex=..., simplified=...)`; join a list of simplified forms yourself (`", ".join(...)`) |

Behaviour differences to be aware of when adopting:

- **Blank feedback.** `EvaluationResult` recorded the tag of a criterion whose feedback was `None` or blank but left it out of the feedback string. `export_feedback` keeps the tag by adding `""`, but lf_toolkit@ae52fa6's `Result.feedback` joins every entry with `<br>`, blanks included, so the string can contain empty segments until the [proposed upstream fix](../docs/refactor/upstream-lf-toolkit.md) lands.
- **Tags in `to_dict()`.** lf_toolkit only includes `tags` with `include_test_data=True`; `EvaluationResult.serialise()` always did.
- **Stripping.** Feedback text is stripped when resolved (it used to be stripped when serialised), so the stored texts are already trimmed.

### Fixed

- Rendering a tree to mermaid no longer empties the tree. The renderer used the root's own `outgoing` list as its work stack.
- The criteria parser builder no longer extends the module-level default token list, so reserved words from one parser no longer leak into every later parser.
- `build_tree` on an unknown label raises a `CriteriaGraphError` (a `ValueError`) naming the label. It used to raise `AttributeError` from formatting the message with the missing node.
- `add_node` works for evaluation nodes (it read a nonexistent `sufficiencies` attribute) and keeps the node's `evaluate` function and a criterion's `feedback_string_generator` (both were dropped).
- Graph nodes are hashable and compare unequal to non-nodes, instead of raising `AttributeError`.
- **Deterministic results.** `generate_feedback` ran evaluations (and so ordered the returned criteria), and `CriteriaGraph.mermaid()` ordered its edge lines, by set iteration, which varies with Python's hash seed. Both now follow graph order: evaluations breadth-first in attachment order. `starting_evaluations` returns an ordered, de-duplicated **list** (was a set).
- `starting_evaluations` terminates when sufficiencies form a cycle; it used to loop forever.
- A failing `evaluate` function raises `CriteriaEvaluationError` (with the original exception chained) instead of printing the evaluation label and the whole evaluations dict to stdout.
