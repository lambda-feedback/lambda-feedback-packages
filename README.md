# Lambda Feedback packages

Reusable packages for Lambda Feedback evaluation functions, originally
extracted from the
[compareExpressions](https://github.com/lambda-feedback/compareExpressions)
evaluation function. Each package is independently installable; together they
share the `lambdafeedback` namespace. The app-specific *core evaluation*
logic stays in compareExpressions.

> **0.2.0:** the post-extraction refactor (branch `refactor/package-tidy`)
> reshaped every package's API. Each package's `CHANGELOG.md` has the
> old → new migration table; [`docs/refactor/`](docs/refactor/README.md) has
> the plan, decisions and per-package checklists.

## Packages

| Directory | Distribution | Import | Responsibility | Depends on |
|---|---|---|---|---|
| `slr_parsing` | `lambdafeedback-slr-parsing` | `lambdafeedback.slr_parsing` | Generic SLR(1) parser engine | — |
| `criteria` | `lambdafeedback-criteria` | `lambdafeedback.criteria` | Criteria DSL parser and evaluation graph | `slr_parsing` |
| `expression_parsing` | `lambdafeedback-expression-parsing` | `lambdafeedback.expression_parsing` | Safe SymPy parsing, preprocessing and LaTeX input/output | `slr_parsing`, `sympy`, `latex2sympy2_extended` |
| `units` | `lambdafeedback-units` | `lambdafeedback.units` | Unit-system data, physical-quantity parsing and dimensional analysis | `slr_parsing`, `expression_parsing`, `sympy` |

```python
from lambdafeedback.expression_parsing import (
    ExpressionParams,
    SympyParsingConfig,
    parse_expression,
    preprocess_expression,
)
from lambdafeedback.units import QuantityParams, parse_quantity

params = ExpressionParams.from_dict(evaluation_params)  # JSON parameters → typed
pre = preprocess_expression("response", response, params)  # aliases, brackets, |x|
expr = parse_expression(pre, SympyParsingConfig.from_params(params))

quantity = parse_quantity("9.81 m/s^2", QuantityParams.from_dict(evaluation_params))  # value, unit, dimension, SI forms
```

`evaluation_result` has been retired: use `lf_toolkit.evaluation.Result`
from [toolkit-python](https://github.com/lambda-feedback/toolkit-python), with
`CriteriaGraph.export_feedback` for criteria feedback.

Each package uses a `src/` layout: `units/src/lambdafeedback/units/`.
There is deliberately no `lambdafeedback/__init__.py`; the namespace is
[PEP 420](https://peps.python.org/pep-0420/), so the separately installed
packages merge under one import root.

Python 3.11 and later is supported.

## Development

The repo root is a non-package [Poetry](https://python-poetry.org/) project
that installs every package in develop mode, plus the tooling, into one venv:

```bash
poetry install                      # creates the venv with all packages + dev tools
poetry run scripts/test.sh -q       # every package's tests (one pytest process each)
poetry run pytest units/tests       # a single package
poetry run ruff check . && poetry run ruff format --check .
poetry run mypy
poetry run python tools/parity/check.py   # diff behaviour against the v0.1 baseline
```

Each package's tests run in their own pytest process, because every package
has a `tests` package and one process can't import two packages with the same
name.

Ruff and mypy cover a package once its refactor phase lands. The
`extend-exclude` list and the mypy `files` list in the root `pyproject.toml`
record which packages are covered so far.

### Parity check

`tools/parity/baseline.json` holds 3221 probe outputs captured from the v0.1
extraction (`tools/parity/capture_v0_1.py`). `tools/parity/check.py` rebuilds
the same probes through the current API. Any difference fails, unless it is
listed in `tools/parity/expected_changes.json` with its reason and exact new
value (bug fixes only).

## Building

Each package builds on its own:

```bash
cd units && poetry build
```

During development, sibling dependencies resolve from the monorepo as path
dependencies. The published metadata keeps plain version requirements.

## Feedback decoupling

The parsing/units code does not resolve feedback text itself, and raises typed
exceptions (`expression_parsing.ExpressionParsingError`,
`units.QuantityError`, both `ValueError`s with structured fields such as
`.expression`) rather than returning feedback tags for failures. Non-fatal
diagnostics stay as plain structured facts instead: `units.PhysicalQuantity`
exposes unit-like text found inside a value as
`reverted_units: list[RevertedUnit]` (`before`/`marked`/`after`). Consumers
decide entirely on their own whether/how to surface any of this as feedback.
`CriteriaGraph.export_feedback` turns reached criteria into feedback on a
result object such as `lf_toolkit.evaluation.Result`; subclass the graph and
override it to export feedback differently.
See [`NOTES.md`](NOTES.md).
