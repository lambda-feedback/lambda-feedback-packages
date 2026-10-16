# Changelog: lambdafeedback-criteria

## 0.3.0 (unreleased; pre-release 0.3.0rc2, tag v0.3.0-rc.2)

The first public release, after the extraction refactor. The import path is now `lambdafeedback.criteria` (was `criteria`). There was no 0.2.0 release: all four `lambdafeedback-*` packages share one version, and the first release is 0.3.0. Supports Python 3.12 to 3.14 (3.11 is not supported); `__version__` gives the installed version.

### Renamed and restructured

| v0.1 | 0.3.0 |
|---|---|
| `criteria` (import) | `lambdafeedback.criteria` |
| `generate_criteria_parser(reserved, token_list=, productions=)` | `build_criteria_parser(reserved, token_list=, productions=)`; the defaults are the tuples `grammar.TOKENS` / `grammar.PRODUCTIONS` |
| `criteria.parsing.base_token_list` / `base_productions` | `criteria.grammar.TOKENS` / `PRODUCTIONS` |
| `CriteriaGraph.Evaluation` / `.Criterion` / `.Output` / `.Edge` / `.Node` | `EvaluationNode` / `CriterionNode` / `OutputNode` / `Edge` / `Node` (module-level dataclasses) |
| `CriteriaGraph.Tree` | `CriteriaTree`, with `children` / `parent` instead of `outgoing` / `incoming` |
| `graph.json()` / `graph.mermaid()` | `graph.to_json()` / `graph.to_mermaid()` |
| `tree.json()` / `tree.mermaid(special_nodes)` / `tree.as_dictionary()` | `tree.to_json()` / `tree.to_mermaid(special_nodes)` / `tree.as_dict()` |
| `graph.build_tree(start, return_node=..., main_criteria=None)` | `graph.build_tree(start, main_criteria=())` |
| `graph.starting_evaluations(label)` returned a `set` | `graph.starting_evaluations(criterion)` returns an ordered `list` |
| `graph.generate_feedback(response, main_criteria)` | `graph.generate_feedback(response, main_criterion)` |

The graph-building methods `add_evaluation_node`, `add_criterion_node`, `add_output_node`, `add_node` and `add_sufficiencies`, and `generate_feedback` and `trees` (but see their parameters below), and node attributes (`label`, `summary`, `details`, `incoming`, `outgoing`, `evaluate`, `replacement`, `feedback_string_generator`) keep their names.

Removed (unused): `CriteriaGraph(identifier, entry_evaluations=)` (never read), `CriteriaGraph.RETURN`, the `Evaluation.results` / `Criterion.consequences` aliases of `outgoing`, and the node `tags` attributes.

Signatures: `add_evaluation_node` no longer accepts `feedback_string_generator`, and `add_criterion_node` no longer accepts `sufficiencies` / `evaluate` (they only existed to serve `attach`). `attach` still takes all three and now raises `CriteriaGraphError` when one doesn't apply to the kind of node it creates; previously `evaluate` for a new criterion was silently ignored. It also raises when `summary`, `details` or any of these options are given for a target that already exists (they used to be silently ignored); callers migrating from v0.1 should check `attach` calls to existing nodes.

Labels are unique across node kinds: adding a node whose label is already used by an evaluation, criterion or output raises `CriteriaGraphError` (previously a criterion could share an evaluation's label and wipe its sufficiencies). `add_node` now keeps an evaluation's `replacement`. An evaluation reporting a criterion not in the graph, a sufficiency naming a non-criterion, and `resolve_feedback` / `export_feedback` for an unknown tag without custom feedback raise `CriteriaGraphError` instead of `KeyError`.

Starting points: `starting_evaluations`, `generate_feedback` and `trees` take a criterion label only; they used to also accept an evaluation label and start there. Passing an evaluation label, or a criterion that no evaluation leads to (which used to give `[]` / no feedback), raises `CriteriaGraphError`. To run from an evaluation, pass a criterion it leads to.

Replacements: `generate_feedback` follows chains of `replacement`s (an evaluation replaced by an evaluation that is itself replaced), stopping on cycles; it used to follow only one step and run the second evaluation. An `evaluate` function returning something other than a mapping raises `CriteriaGraphError` naming the evaluation (it was an opaque `ValueError` from `dict.update`). `generate_feedback` is annotated as returning `ReachedCriteria`.

Rendering: `to_mermaid()` draws sufficiency edges between the real nodes (they pointed at new, unconnected boxes named after the labels) and escapes `"` in labels and text; tree mermaid ids are safe for labels with spaces or punctuation. Tree children are in attachment order (they were reversed), and tree mermaid declares nodes in that order, which mermaid uses to lay out siblings. Tree identifiers are unique (the root and the first child both used `_0`). `Evaluate` and `FeedbackStringGenerator` are exported for type hints.

Errors: graph misuse raises `CriteriaGraphError` (a `ValueError`) instead of bare `Exception`; `CriteriaError` is the common base.

Modules: `grammar` (was `parsing`), `nodes`, `graph`, `tree`, `render`, `errors`. Fully type-annotated (`py.typed`).

Packaging: README (PyPI description), MIT licence and project metadata.

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

### Added

- `build_quantity_criteria_parser(reserved_expressions, token_list=, productions=)` parses criteria on physical quantities (`response matches answer`, `dimension(response) matches dimension(answer)`, and `=`, `<=`, `>=`, `<`, `>` between quantities). Its defaults are `quantity_grammar.QUANTITY_TOKENS` / `QUANTITY_PRODUCTIONS`. It was `generate_criteria_parser` in compareExpressions' physical-quantity context, and its parse trees are unchanged. It takes the same arguments as `build_criteria_parser`, so either can fill the same slot. `reserved_expressions` isn't used yet: only `response` and `answer` scan as quantities.
- `split_criteria(criteria)` splits a string of criteria on the commas outside `()`, `[]` and `{}`, and strips each criterion. It was `split_criteria` in compareExpressions' `evaluation.py`. Unlike that version, it raises `CriteriaSyntaxError` (new, a `CriteriaError` and `ValueError`) when a bracket is closed before it is opened, or left open. The old version stopped splitting at the first such bracket instead.

### Changed

- DEBUG logging through module loggers (`lambdafeedback.criteria.*`), with a `NullHandler` on the package logger; nothing is logged at INFO or above. See the repository README. `generate_feedback` logs each evaluation run, the criteria it reported and replacements followed.
- `attach(source, target)` only connects existing nodes. `attach_new_criterion(evaluation, label, summary, details, feedback_string_generator=None)` and `attach_new_evaluation(criterion, label, summary, details, sufficiencies=(), evaluate=None)` create the target and attach it (`attach` used to do both, with keywords valid for one node kind or the other).
- `CriteriaGraph.END` (one `OutputNode` shared by every graph) is replaced by `graph.add_end_node()` and `CriteriaGraph.END_LABEL`. `EvaluationNode.replacement` is a node label (was a node); `generate_feedback` raises `CriteriaGraphError` if it names neither an evaluation nor an output.
- Sufficiencies are stored on the node: `EvaluationNode.sufficiencies`, a tuple, replaces `CriteriaGraph.sufficiencies`, and `add_node` copies them. An empty list means no sufficiencies (it used to remove the evaluation from the starting evaluations).
- Nodes compare by identity (they compared by label, summary and details, all mutable).

### Fixed

- Rendering a tree to mermaid no longer empties the tree. The renderer used the root's own `outgoing` list as its work stack.
- The criteria parser builder no longer extends the module-level default token list, so reserved words from one parser no longer leak into every later parser.
- `build_tree` on an unknown label raises a `CriteriaGraphError` (a `ValueError`) naming the label. It used to raise `AttributeError` from formatting the message with the missing node.
- `add_node` works for evaluation nodes (it read a nonexistent `sufficiencies` attribute) and keeps the node's `evaluate` function and a criterion's `feedback_string_generator` (both were dropped).
- Graph nodes are hashable and compare unequal to non-nodes, instead of raising `AttributeError`.
- **Deterministic results.** `generate_feedback` ran evaluations (and so ordered the returned criteria), and `CriteriaGraph.mermaid()` ordered its edge lines, by set iteration, which varies with Python's hash seed. Both now follow graph order: evaluations breadth-first in attachment order. `starting_evaluations` returns an ordered, de-duplicated **list** (was a set).
- `starting_evaluations` terminates when sufficiencies form a cycle; it used to loop forever.
- Reserved names are matched literally. They were used as regular expressions, so a name such as `x.y` also matched `xzy`, and one such as `f(x)` never matched itself. `grammar.TOKENS` are now `slr_parsing.Lexeme`s; a custom `token_list` needs literal or `Lexeme` patterns too.
- A failing `evaluate` function raises `CriteriaEvaluationError` (with the original exception chained) instead of printing the evaluation label and the whole evaluations dict to stdout.
