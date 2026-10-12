# lambdafeedback-criteria

Criteria for [Lambda Feedback](https://github.com/lambda-feedback) evaluation
functions: a parser for criteria such as `response = answer where x = 1`, and
criteria graphs that run evaluations on a response, follow the criteria they
establish and turn them into feedback.

Originally extracted from the
[compareExpressions](https://github.com/lambda-feedback/compareExpressions)
evaluation function.

## Install

From git (not on PyPI yet):

```bash
pip install "lambdafeedback-criteria @ git+https://github.com/lambda-feedback/lambda-feedback-packages.git@v0.3.0#subdirectory=criteria"
```

Install the packages it depends on (`slr_parsing`) from the same tag; see the [repository README](../README.md#install).

Requires Python 3.11+. The import root is `lambdafeedback.criteria`. The only
dependency is
[`lambdafeedback-slr-parsing`](../slr_parsing/README.md).

## Parsing criteria

`build_criteria_parser` takes the reserved expressions, grouped (for example
by who supplies them), as `{group: {name: expression}}`. Only the names are
used: they scan as `RESERVED`, and any other text scans as `OTHER`.

```python
from lambdafeedback.criteria import build_criteria_parser

parser = build_criteria_parser({"learner": {"response": None}, "task": {"answer": None}})
(root,) = parser.parse(parser.scan("response = answer where x = 1"))
print(root.tree_string())
# WHERE:  where  tags: {}
# 0: EQUALITY:  =  tags: {}
# |   0: RESERVED: response tags: {}
# |   1: RESERVED: answer tags: {}
# 1: EQUALITY:  =  tags: {}
#     0: OTHER: x tags: {}
#     1: OTHER: 1 tags: {}
```

The parser returns a `lambdafeedback.slr_parsing` expression tree. The
criteria it accepts, by root label:

| Criterion | Root label |
|---|---|
| `a = b` | `EQUALITY` |
| `a < b`, `a <= b`, `a > b`, `a >= b` | `ORDER` |
| `a proportional to b` | `PROPORTIONAL_TO` |
| `response written as answer` (reserved names on the left) | `WRITTEN_AS` |
| `response contains x` (reserved name on the left) | `CONTAINS` |
| `<equality or order> where x = 1` or `where x = 1; y = 2` | `WHERE` |

To extend the language, pass your own `token_list` and `productions`. The
defaults are `lambdafeedback.criteria.grammar.TOKENS` and `PRODUCTIONS`.

## Criteria graphs

A `CriteriaGraph` alternates between two kinds of node:

- **evaluation nodes** run a check on the response and report which criteria
  hold, with the inputs for each criterion's feedback text;
- **criterion nodes** record an outcome and lead to further evaluations or to
  **output nodes** such as the conventional `END` (`graph.add_end_node()`).

```python
from lambdafeedback.criteria import CriteriaGraph


def compare(response):
    if response == "x + 1":
        return {"EQUAL": None}
    return {"NOT_EQUAL": {"response": response}}


graph = CriteriaGraph("response = answer")
graph.add_end_node()
graph.add_evaluation_node("COMPARE", "response = answer", "Compare the response with the answer", evaluate=compare)
graph.attach_new_criterion(
    "COMPARE", "EQUAL", "equal", "The response equals the answer", feedback_string_generator=lambda inputs: "Correct."
)
graph.attach_new_criterion(
    "COMPARE",
    "NOT_EQUAL",
    "not equal",
    "The response differs from the answer",
    feedback_string_generator=lambda inputs: f"{inputs['response']} is not the answer.",
)
graph.attach("EQUAL", "END")
graph.attach("NOT_EQUAL", "END")

reached = graph.generate_feedback("2*x", "EQUAL")
# {'NOT_EQUAL': {'response': '2*x'}}
graph.resolve_feedback(reached)
# [('NOT_EQUAL', '2*x is not the answer.')]
```

- `attach_new_criterion(evaluation, label, summary, details, ...)` and
  `attach_new_evaluation(criterion, label, summary, details, ...)` add a node
  and the edge to it, so a graph can be built mostly from these calls.
  `attach(source, target)` adds an edge between existing nodes. Labels are
  unique across all nodes.
- `generate_feedback(response, criterion)` starts from the evaluations that
  lead to `criterion`, runs every evaluation it reaches (breadth-first, in
  attachment order) and returns the criteria reached. Whether `criterion` is
  among them tells you whether it holds.
- `export_feedback(result, reached, custom_feedback=None)` adds the feedback to
  a result object with `tags` and `add_feedback(tag, text)`, such as
  `lf_toolkit.evaluation.Result` (see the `ResultLike` protocol).
  `custom_feedback` overrides the text for given criteria.
- **Sufficiencies** (`add_sufficiencies`) let an evaluation be skipped when
  starting, in favour of the evaluations leading to other criteria.
- Setting an evaluation node's `replacement` to another node's label (for
  example `CriteriaGraph.END_LABEL`) disables it: feedback generation goes to
  that node instead.

## Rendering

`graph.to_json()` and `graph.to_mermaid()` render the whole graph.
`graph.trees(criterion)` unrolls it into display trees from each starting
evaluation, with their own `to_json()`, `as_dict()` and `to_mermaid()`.
`CriteriaGraph.test_data(graphs)` bundles the JSON and mermaid renderings of
several graphs for a result's test data.

## Errors

All exceptions derive from `CriteriaError`:

| Exception | Raised when |
|---|---|
| `CriteriaGraphError` (also a `ValueError`) | the graph is built or queried inconsistently: duplicate or unknown labels, wrong node kinds, an evaluation returning unknown criteria or a non-mapping, ... |
| `CriteriaEvaluationError` | an evaluation's `evaluate` function raised; the original exception is chained as `__cause__`, and `.label` names the evaluation |

## Changelog

See [CHANGELOG.md](https://github.com/lambda-feedback/lambda-feedback-packages/blob/main/criteria/CHANGELOG.md).

## License

MIT
