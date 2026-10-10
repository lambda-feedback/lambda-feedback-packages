# Extraction & decoupling notes

> Historical: these notes describe the v0.1 extraction. For the current
> packages, dependencies and API, see the [README](README.md) and each
> package's `CHANGELOG.md`.

These packages were extracted from the
[compareExpressions](https://github.com/lambda-feedback/compareExpressions)
evaluation function. The reusable machinery (a generic parser, SymPy expression
parsing, a unit system + dimensional analysis, a criteria DSL, a result
container) previously lived under `app/utility/` and
`app/preview_implementations/`, interwoven with the app-specific *core
evaluation* (`app/evaluation.py`, `app/context/*`) and *feedback strings*
(`app/feedback/*`).

The extraction copied the reusable modules out **without editing `app/`** (the
live function was never touched — verified via `git diff`). The obstacles below
are the coupling that had to be severed or rewired to make the copies stand
alone.

## Package dependency graph

```
slr_parsing          (no deps)
evaluation_result    (no deps)
criteria             -> slr_parsing
expression_parsing   -> slr_parsing, sympy, latex2sympy2
units                -> slr_parsing, expression_parsing, sympy
```

Install editable in this order (later packages depend on earlier ones):

```bash
pip install -e slr_parsing -e evaluation_result -e criteria \
            -e expression_parsing -e units
```

*(As extracted. Since the refactor, the packages live under the
`lambdafeedback.*` namespace and install via Poetry; see
[Refactor](#refactor-stage-2) below and the README.)*

---

## 1. Back-dependency on app feedback strings (main issue)

The parsing/units utilities imported `app/feedback/*` to resolve human-readable
feedback text inline. A reusable package cannot carry the app's feedback
catalogue, so this dependency had to be severed. It was confined to 3 modules /
~6 call sites:

| Module | Site | Feedback tag |
|---|---|---|
| `expression_parsing/expression_utilities.py` | `convert_bracket_notation` | `BRACKET_NOTATION_MISMATCH` |
| `expression_parsing/expression_utilities.py` | `convert_absolute_notation` | `ABSOLUTE_VALUE_NOTATION_AMBIGUITY` |
| `expression_parsing/symbolic_preview.py` | parse failure (raised as exception message) | `PARSE_ERROR` |
| `units/physical_quantity_utilities.py` | reverted-unit message | `REVERTED_UNIT` |

**Decision:** introduce `expression_parsing.FeedbackTag(tag, inputs)` — a small
`namedtuple` defined in `expression_parsing/feedback.py`. Instead of resolving a
string, the code now surfaces the feedback *tag* plus the *inputs* needed to
render it. The consumer (e.g. compareExpressions, via its existing
`app/feedback/symbolic.py` and `app/feedback/physical_quantity.py` generators)
owns the `tag -> string` mapping.

```python
# before (in-app):
return expr, (tag, feedback_string_generators["INTERNAL"](tag)({'x': expr}))

# after (extracted, app-agnostic):
return expr, (tag, FeedbackTag(tag, {'x': expr}))
```

**Contract change to be aware of:** call sites that previously carried a
resolved string now carry a `FeedbackTag`. This applies to the `(expr, feedback)`
tuples returned by the conversion helpers, the `SyntaxError` payload raised by
`symbolic_preview`, and the `PhysicalQuantity.messages` entries. A consumer must
map these tags to strings before displaying them.

## 2. Cross-layer dependency: units → preview implementation

`physical_quantity_utilities` called
`preview_implementations.symbolic_preview.preview_function` (an app-layer
rendering module) to render the numeric value part of a quantity.

**Decision:** move `symbolic_preview` into the `expression_parsing` package,
since it is generic "parse symbolic expression → LaTeX/SymPy" logic rather than
app-specific. `units` now depends on `expression_parsing` cleanly, instead of
reaching into the app layer. `physical_quantity_preview` was likewise pulled into
`units` as the quantity-rendering counterpart.

## 3. Import rewiring

All relative imports were repointed to the new package boundaries:

- `from .slr_parsing_utilities import ...`      → `from slr_parsing import ...`
- `from .syntactical_comparison_utilities ...`  → `from .syntactical_comparison ...`
- `from ..utility.expression_utilities import ...` → `from expression_parsing... import ...`
- `from ..preview_implementations.symbolic_preview ...` → `from expression_parsing.symbolic_preview ...`
- `from ..feedback... import feedback_string_generators` → removed (see §1)

## 4. Packaging

Each package is a PEP 621 project with its own `pyproject.toml` (setuptools
backend, `requires-python >= 3.8`). Local cross-package dependencies are
declared by distribution name (`lambdafeedback-slr-parsing`,
`lambdafeedback-expression-parsing`). External runtime deps: `sympy`,
`latex2sympy2`, `typing_extensions`.

---

## Non-issues (carried over verbatim, not introduced here)

- **`SyntaxWarning: invalid escape sequence`** in regex string literals
  (`syntactical_comparison.py`, `expression_utilities.py`, `preview_utilities.py`)
  — pre-existing in the original code.
- **SymPy deprecation warnings** (non-`Expr` args in `Mul`) — pre-existing;
  surface when running the original test suite too.

Both are candidates for a follow-up cleanup but were intentionally left
unchanged to keep the extraction a faithful copy.

## Verification performed

- Editable-installed all five packages into a fresh venv in dependency order.
- Smoke-tested each package, including `units` parsing `2 kg m/s^2`
  → `2 | kilogram metre/second^2`, and confirmed the severed feedback sites
  return `FeedbackTag` payloads rather than strings.
- Confirmed `app/` was unmodified and its full test suite still passed
  (3128 passed, 4 skipped) — the extraction is copy-only.

## Follow-up (out of scope of the extraction)

Adopting these packages back into compareExpressions: rewire `app/` imports to
the packages and add the `tag -> string` resolution at the consumer boundary
using the existing `app/feedback/*` generators.

---

## Refactor (stage 2)

The extraction deliberately kept the code verbatim. Stage 2 reshapes the
packages before compareExpressions adopts them. The plan and per-package
checklists are in [`docs/refactor/`](docs/refactor/README.md); the key
decisions are:

- **Break APIs freely**, since nothing depends on the packages yet. PEP 8
  names and typed data replace positional tuples and free-form `params`
  dicts. Each package's `CHANGELOG.md` records old → new.
- **Fix latent bugs**, each with a regression test. The bugs include inputs
  that currently crash or mis-parse (`2E`, `2 litres` → litre·second,
  `(2 m) s`), in-place mutation of caller `params`, and `eval()` of
  author-supplied `symbol_assumptions`.
- **Namespace + layout:** `lambdafeedback.<pkg>` (PEP 420), `src/` layout,
  Poetry, with a root dev environment.
- **Retire `evaluation_result`** in favour of `lf_toolkit.evaluation.Result`
  from [toolkit-python](https://github.com/lambda-feedback/toolkit-python).
  Its criteria-specific parts are now `CriteriaGraph` methods
  (`resolve_feedback`, `export_feedback`, `test_data`). For now the
  packages only *type* against lf_toolkit (a `ResultLike` protocol and
  structurally identical TypedDicts), because lf_toolkit@ae52fa6 installs
  ~237 MB of dev tools it declares as runtime requirements. It is a dev-only
  dependency until the drafted upstream fixes land.
- **latex2sympy2 from PyPI**, not the lambda-feedback fork, so that the
  packages stay publishable. `parse_latex` reproduces the fork's relevant
  change itself: `x = 2` is an equation, not an assignment.
- **Python 3.11–3.12.** 3.13 is blocked by latex2sympy2's pin on
  `antlr4-python3-runtime` 4.7.2.

Behaviour is guarded by a parity baseline (`tools/parity/`) captured from the
extracted v0.1 code: 3221 probes, of which 92 changed, each a reviewed bug fix
recorded in `tools/parity/expected_changes.json` and the changelogs. Over 40
latent bugs were fixed in total (including an `eval()` code-injection path, two
hangs and several mis-parses), each with a regression test. Tests went from 468
to 611.
