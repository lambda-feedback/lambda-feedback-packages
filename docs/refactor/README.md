# Refactor & tidy-up

This is the second stage after the extraction described in [`NOTES.md`](../../NOTES.md). The extraction was a faithful copy of the original code. This stage reshapes the packages before compareExpressions adopts them.

Each package has a checklist, and commits tick off items as they land:

| Order | Checklist | Package |
|---|---|---|
| 0 | [scaffolding.md](scaffolding.md) | Repo layout, Poetry, ruff, mypy, CI |
| 1 | [slr_parsing.md](slr_parsing.md) | `lambdafeedback.slr_parsing` |
| 2 | [criteria.md](criteria.md) | `lambdafeedback.criteria` (and retiring `evaluation_result`) |
| 3 | [expression_parsing.md](expression_parsing.md) | `lambdafeedback.expression_parsing` |
| 4 | [units.md](units.md) | `lambdafeedback.units` |

Baseline before the refactor: **468 tests pass** (10 slr_parsing, 7 evaluation_result, 10 criteria, 157 expression_parsing, 284 units). After: **611** (45 slr_parsing, 47 criteria, 204 expression_parsing, 315 units; evaluation_result retired). **All four phases are done.**

## Agreed decisions

| Topic | Decision |
|---|---|
| Public API | Break freely: PEP 8 names and cleaner signatures. Each package gets a `CHANGELOG.md` with an old→new migration table. Version goes to `0.2.0`. |
| Bugs | Fix each one in its own commit, with a regression test that fails first. Behaviour changes go in the changelog. |
| Structure | Split large modules; typed data (NamedTuple/dataclass/Enum); a per-package exception hierarchy; a typed params dataclass in place of free-form `params` dicts. |
| Tooling | Poetry, ruff (lint + format), mypy, GitHub Actions CI. Python floor **3.11**, which lf_toolkit requires. |
| Import names | PEP 420 namespace: `lambdafeedback.slr_parsing`, `.criteria`, `.expression_parsing`, `.units`. Distribution names stay `lambdafeedback-<pkg>`. |
| Layout | `src/` layout per package, plus a root non-package Poetry project (`package-mode = false`) that path-installs every package into one dev venv. |
| evaluation_result | **Retired** (Phase 2). Generic result handling moves to `lf_toolkit.evaluation.Result`; criteria-specific helpers are `CriteriaGraph` methods; `export_feedback` records blank feedback as `""` so tags are kept. |
| lf_toolkit | **Structural typing for now** (revised in Phase 2). lf_toolkit@ae52fa6 declares its dev tools (boto3, pillow, pydantic, ...) as runtime requirements: 80 packages / 237 MB. So our packages use a `ResultLike` protocol and TypedDicts structurally identical to lf_toolkit's, and lf_toolkit is a **dev-only** dependency (pinned git) for compatibility tests. It becomes a real dependency once [the upstream fixes](upstream-lf-toolkit.md) land. |
| FeedbackTag | Stays in `expression_parsing` as a frozen dataclass plus a `StrEnum` of tag names. Consumers resolve tags to strings before `Result.add_feedback(tag, str)`. |
| latex2sympy2 | **PyPI release, not the fork** (decided in Phase 3). A git pin would make the packages unpublishable. The fork's relevant change (`x = 2` → `Eq(x, 2)` rather than an assignment) is reproduced by `parse_latex` splitting `=` itself. |

## Working conventions

- Branch `refactor/package-tidy`, one commit per checklist item.
- Package order follows the dependency graph: slr_parsing → criteria → expression_parsing → units.
- Within a package: (1) move the layout with no code changes, tests green; (2) regression test and fix for each bug; (3) restructure without changing behaviour; (4) rename the API and write the migration table; (5) types and mypy; (6) ruff.
- Carry over the SymPy-heavy tests with only their imports and call shapes changed, so they act as a parity check.

## Verification

- [x] Before Phase 1: save a JSON snapshot of outputs for every carried-over test input (`parse_expression` str/latex, both `preview_function`s, quantity value/unit/standard forms). This is `tools/parity/baseline.json` (3221 probes).
- [x] After each package: `poetry run python tools/parity/check.py` passes. 92 of 3221 probes changed, each a reviewed bug fix listed in `tools/parity/expected_changes.json` and noted in the changelogs.
- [x] `ruff check`, `ruff format --check`, `mypy` and `scripts/test.sh` pass for all packages (checked locally on 3.12; CI runs 3.11 and 3.12. 3.13 is blocked; see Risks).
- [x] No `SyntaxWarning`s (pytest turns them into errors); no `print(` or `eval(` left in `src/`.
- [x] Adoption smoke test in a clean venv with the four built 0.2.0 wheels: `parse_quantity("2 kg m/s^2", QuantityParams.from_dict({...}))` → `2 | kilogram metre/second^2`. Both `preview_function`s return results matching lf_toolkit's `Result` shape (tested against the real class in the dev env). Runtime dependencies are only sympy and latex2sympy2.

## Risks / open items

- **lf_toolkit is git-only** (not on PyPI) and **ships its dev tools as runtime requirements**. Both block a hard dependency; see [upstream-lf-toolkit.md](upstream-lf-toolkit.md) for the drafted fixes (including skipping blank entries in `Result.feedback`).
- **Parity with compareExpressions:** several bug fixes change results for some inputs. The changelogs list each one so adoption can re-run compareExpressions' 3128-test suite with them in mind.
- ~~Poetry path-dependency enrichment~~: checked in Phase 0. Built wheels carry only plain requirements.
- ~~**Python 3.13 is blocked**~~ (resolved in 0.3.0: `expression_parsing` moved to latex2sympy2_extended, which supports newer ANTLR runtimes) for `expression_parsing` and `units`: latex2sympy2 pins `antlr4-python3-runtime` 4.7.2, which imports `typing.io`, removed in 3.13. Both the PyPI release and the lambda-feedback fork are affected. Lifting this needs latex2sympy regenerated with a newer ANTLR (upstream work).
