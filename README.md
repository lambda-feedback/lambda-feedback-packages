# Lambda Feedback packages

Reusable packages for Lambda Feedback evaluation functions, originally
extracted from the
[compareExpressions](https://github.com/lambda-feedback/compareExpressions)
evaluation function. Each package is independently installable; together they
share the `lambdafeedback` namespace. The app-specific *core evaluation*
logic stays in compareExpressions.

The extraction refactor reshaped every package's API. Each package's
`CHANGELOG.md` has the old → new migration table.

## Install

The packages are distributed through git for now (not PyPI), from a release
tag. They depend on each other by version, so install the ones you use
**and the packages they depend on** from the same tag:

```bash
pip install "lambdafeedback-slr-parsing @ git+https://github.com/lambda-feedback/lambda-feedback-packages.git@v0.3.0-rc.4#subdirectory=slr_parsing"
pip install "lambdafeedback-criteria @ git+https://github.com/lambda-feedback/lambda-feedback-packages.git@v0.3.0-rc.4#subdirectory=criteria"
pip install "lambdafeedback-expression-parsing @ git+https://github.com/lambda-feedback/lambda-feedback-packages.git@v0.3.0-rc.4#subdirectory=expression_parsing"
pip install "lambdafeedback-physical-quantities @ git+https://github.com/lambda-feedback/lambda-feedback-packages.git@v0.3.0-rc.4#subdirectory=physical_quantities"
```

With Poetry: `lambdafeedback-physical-quantities = { git = "https://github.com/lambda-feedback/lambda-feedback-packages.git", tag = "v0.3.0-rc.4", subdirectory = "physical_quantities" }`, and likewise for each package.

## Packages

| Directory | Distribution | Import | Responsibility | Depends on |
|---|---|---|---|---|
| `slr_parsing` | `lambdafeedback-slr-parsing` | `lambdafeedback.slr_parsing` | Generic SLR(1) parser engine | — |
| `criteria` | `lambdafeedback-criteria` | `lambdafeedback.criteria` | Criteria DSL parser and evaluation graph | `slr_parsing` |
| `expression_parsing` | `lambdafeedback-expression-parsing` | `lambdafeedback.expression_parsing` | Safe SymPy parsing, preprocessing and LaTeX input/output | `slr_parsing`, `sympy`, `latex2sympy2_extended` |
| `physical_quantities` | `lambdafeedback-physical-quantities` | `lambdafeedback.physical_quantities` | Unit-system data, physical-quantity parsing and dimensional analysis | `slr_parsing`, `expression_parsing`, `sympy` |

```python
from lambdafeedback.expression_parsing import (
    ExpressionParams,
    SympyParsingConfig,
    parse_expression,
    preprocess_expression,
)
from lambdafeedback.physical_quantities import QuantityParams, parse_quantity

params = ExpressionParams.from_dict(evaluation_params)  # JSON parameters → typed
pre = preprocess_expression(response, params, name="response")  # aliases, brackets, |x|
expr = parse_expression(pre, SympyParsingConfig.from_params(params))

quantity = parse_quantity("9.81 m/s^2", QuantityParams.from_dict(evaluation_params))  # value, unit, dimension, SI forms
```

`evaluation_result` has been retired: use `lf_toolkit.evaluation.Result`
from [toolkit-python](https://github.com/lambda-feedback/toolkit-python), with
`CriteriaGraph.export_feedback` for criteria feedback.

Each package uses a `src/` layout: `physical_quantities/src/lambdafeedback/physical_quantities/`.
There is deliberately no `lambdafeedback/__init__.py`; the namespace is
[PEP 420](https://peps.python.org/pep-0420/), so the separately installed
packages merge under one import root.

Python 3.12 and later is supported.

## Development

The repo root is a non-package [Poetry](https://python-poetry.org/) project
that installs every package in develop mode, plus the tooling, into one venv:

```bash
poetry install                      # creates the venv with all packages + dev tools
poetry run scripts/test.sh -q       # every package's tests (one pytest process each)
poetry run pytest physical_quantities/tests  # a single package
poetry run ruff check . && poetry run ruff format --check .
poetry run mypy
poetry run python tools/parity/check.py   # diff behaviour against the v0.1 baseline
```

Each package's tests run in their own pytest process, because every package
has a `tests` package and one process can't import two packages with the same
name.

CI runs all of these, on Python 3.12 to 3.14.

### Parity check

`tools/parity/baseline.json` holds 1608 probe outputs captured from the v0.1
extraction (compareExpressions' code). `tools/parity/check.py` rebuilds
the same probes through the current API. Any difference fails, unless it is
listed in `tools/parity/expected_changes.json` with its reason and exact new
value (bug fixes only).

## Building and releasing

Each package builds on its own:

```bash
cd units && poetry build
```

During development, sibling dependencies resolve from the monorepo as path
dependencies. The published metadata keeps plain version requirements.
`poetry run python scripts/check_dist.py` builds all four, checks the
wheels and sdists (namespace layout, `py.typed`, no local requirements,
tests and changelog in the sdist), installs the wheels into a fresh venv
and runs a smoke test; CI runs it with `twine check`.

The four packages share one version and are released together, through git
(nothing is published to PyPI yet). Bump every `pyproject.toml` and the
`>=lower,<upper` ranges between the packages, then push a tag:

- **Release:** `vMAJOR.MINOR.PATCH` (e.g. `v0.4.0`) runs `release.yml`.
- **Pre-release:** `vMAJOR.MINOR.PATCH-alpha.N`, `-beta.N` or `-rc.N` (e.g.
  `v0.4.0-rc.1`) runs `prerelease.yml`. Python spells it `0.4.0rc1` in
  `pyproject.toml`, and the ranges must admit it: `>=0.4.0rc1,<0.5.0`.

Both run `build-release.yml`: `scripts/release_version.py` checks the tag
against every package's version and the ranges between them, then the tests,
`scripts/check_dist.py` and `twine check` run, and the wheels and sdists are
attached to a GitHub Release (marked as a pre-release for pre-release tags).

## Logging

The packages log at DEBUG only, through loggers named after their modules
(`lambdafeedback.expression_parsing.preprocessing`, `lambdafeedback.physical_quantities.quantity`, ...):
how a response was preprocessed and read, how a quantity was split into value
and unit, which evaluations a criteria graph ran. Failures are exceptions, not
log records. To see them:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("lambdafeedback.slr_parsing").setLevel(logging.INFO)  # the parser trace is verbose
```

## Feedback decoupling

The parsing/units code does not resolve feedback text itself, and raises typed
exceptions (`expression_parsing.ExpressionParsingError`,
`units.QuantityError`, both `ValueError`s with structured fields such as
`.expression`) rather than returning feedback tags for failures. Non-fatal
diagnostics stay as plain structured facts instead: `units.PhysicalQuantity`
exposes unit-like text found inside a value as
`reverted_units: tuple[RevertedUnit, ...]` (`before`/`marked`/`after`). Consumers
decide entirely on their own whether/how to surface any of this as feedback.
`CriteriaGraph.export_feedback` turns reached criteria into feedback on a
result object such as `lf_toolkit.evaluation.Result`; subclass the graph and
override it to export feedback differently.
