# Phase 3: `lambdafeedback.expression_parsing`: done

Depends on `slr_parsing`, `sympy` and `latex2sympy2` (the PyPI release; see below). Released as `0.2.0`; see [`expression_parsing/CHANGELOG.md`](../../expression_parsing/CHANGELOG.md) for the migration table.

> **0.3.0:** preview and feedback-tag code (`preview.py`, `feedback.py`) and `PATTERNS` moved to compareExpressions; preprocessing raises typed exceptions instead of returning `Preprocessed`; `parse_expression` evaluates only mathematics (`_safe_parse.py`). The table below is current.

## Modules

| Module | Contents |
|---|---|
| `params.py` | `ExpressionParams` (frozen; `from_dict` maps the JSON names; symbols normalised once), `SymbolSpec`, `Convention`, `parse_symbol_assumptions` |
| `symbol_tables.py` | `ELEMENTARY_FUNCTIONS`, `GREEK_SYMBOLS` (`SymbolAliases` tuples), `UNICODE_DASHES`, `PLUS_MINUS`/`MINUS_PLUS` |
| `_scanning.py` | Bracket constants and `find_matching_parenthesis` (no package dependencies) |
| `preprocessing.py` | `create_expression_set`, bracket and absolute-value conversion, `preprocess_expression` → `str` (raises `BracketNotationError`/`AbsoluteValueNotationError` with a best guess) |
| `substitution.py` | `substitute`, `FunctionName`, `substitute_input_symbols` (pure), Greek/function substitutions, `normalise_unicode_operators` |
| `conventions.py` | `convention_parser` (cached), `apply_convention` |
| `sympy_parsing.py` | `SympyParsingConfig` (the `ExpressionParams` plus what is derived from them), `parse_expression`, `sympy_symbols` |
| `latex.py` | `sympy_to_latex`, `parse_latex`, `sanitise_latex`, `E`/`e` placeholder handling |
| `_safe_parse.py` | `safe_parse_expr`: SymPy's parse pipeline with a syntax allowlist and a maths-only namespace |
| `numbers.py` | Number scanners (no regexes), `is_number`, complex-form checks, `generate_arbitrary_number_pattern_matcher`, `compute_relative_tolerance_from_significant_decimals` |
| `errors.py` | `ExpressionParsingError` (a `ValueError`) → `InvalidParameterError`, `UnknownConventionError`, `SymbolAssumptionError`, `LatexParseError`, `BracketNotationError`, `AbsoluteValueNotationError` |

**Deviations from the plan:**
- **latex2sympy2 stays on PyPI**, not the lambda-feedback fork (decided in Phase 3; in 0.3.0 both were replaced by latex2sympy2_extended, see the changelog): a git pin would make the packages unpublishable. The fork's relevant behaviour (`x = 2` → `Eq(x, 2)`, where PyPI's release treats it as an assignment) is reproduced by `parse_latex` splitting `=` itself.
- **`preview_function` accepts a plain mapping** as well as `ExpressionParams`, since it is an evaluation-function entry point that receives JSON parameters. Internal functions take `ExpressionParams`.
- **`Preview.feedback` is `NotRequired`** (lf_toolkit's is required). Adding `"feedback": ""` would change every preview's output, so a preview dict has the same keys as before.
- **`parse_expression` still doesn't substitute symbol aliases**, as in v0.1: callers run `preprocess_expression` first. `SympyParsingConfig.substitution_params` records the narrow substitutions it does apply.
- **`typing_extensions` is dropped** (only `NotRequired` was used; it's in `typing` since 3.11).

## Checklist

### Bugs (regression test, one commit each)

- [x] **Security:** `symbol_assumptions` was passed to `eval()` → `ast.literal_eval` + `Symbol(name, **{assumption: True})`.
- [x] `2E` / `xE` failed to parse (root cause in slr_parsing).
- [x] `substitute_input_symbols` overwrote a user-defined `lambda` on the second call (3 previews now show the task's LaTeX).
- [x] Empty-alias removal shifted indices and dropped real aliases; `.strip()` results discarded; same in legacy `input_symbols`.
- [x] `create_expression_set("plus_minus")` raised `IndexError`.
- [x] `a=b=c` silently parsed as `Eq(a, b)` (7 probes now errors).
- [x] `preview_function` / `parse_latex` mutated the caller's params; `sympy_to_latex` mutated `settings`.
- [x] `create_sympy_parsing_params` raised `KeyError` without pre-merged defaults.
- [x] `parse_latex` printed alias errors and raised a tuple-message `ValueError`; `"\pm"` escape.
- [x] SymPy `Mul(FiniteSet, …)` deprecation (strict `{x+1}*{x-1}`) → `ExpressionParsingError` (2 probes).
- [x] **Found during the refactor:** `sanitise_latex` looped forever on an unclosed `\mathrm{`/`\text{`, which learner LaTeX in units' preview could trigger.
- [x] **Found during the refactor:** PyPI latex2sympy2 treated `x = 2` as an assignment (see above).

### Restructure / API

- [x] Four modules split into the eleven above; the old modules are removed.
- [x] `ExpressionParams` / `SympyParsingConfig` replace the params dicts; nothing mutates its parameters.
- [x] Symbols normalised once. The consistent `lambda` → `lamda` handling changes 4 parity probes (reviewed).
- [x] Convention parser cached per convention; deterministic expression-set and substitution ordering.
- [x] Dead code removed (`printing_symbols`, atol/rtol copying, unused ± placeholders, template docstrings).
- [x] Documented why `escape_regex_reserved_characters` isn't `re.escape`. (Since removed with the other regexes; see the 0.3.0 changelog.)
- [x] `units` ported to the new API.

### Types & lint

- [x] mypy with typed definitions required (SymPy and latex2sympy2 treated as `Any`); ruff lint and format; no `SyntaxWarning`s or `print`/`eval` in `src/`.

### Tests (157 → 204)

- [x] `test_regressions.py` (one per bug), `test_api.py` (params, config, conventions, LaTeX, preview shape vs lf_toolkit), carried-over suites ported to the typed API.
