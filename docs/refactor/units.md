# Phase 4: `lambdafeedback.units`: done

Depends on `slr_parsing`, `expression_parsing` and `sympy`. Released as `0.2.0`; see [`units/CHANGELOG.md`](../../units/CHANGELOG.md) for the migration table and known issues.

**Post-refactor cleanup (0.3.0):** `parse_quantity`/`preprocess_quantity` now require `QuantityParams` (no raw-dict fallback); `strictness="legacy"` is deprecated (still works, warns); `preview_function`/`fix_exponents` moved out to compareExpressions (`app/context/physical_quantity_preview.py`) since previewing a response is a display concern, not unit conversion. `FeedbackTag` is gone (mirroring `expression_parsing`'s exception conversion); `PhysicalQuantity.messages` is now `reverted_units: list[RevertedUnit]`, plain `before`/`marked`/`after` facts with no tag name or synthetic id — mapping a fact to feedback text is left entirely to the evaluation function. See the CHANGELOG for details.

## Modules

| Module | Contents |
|---|---|
| `data.py` (was `unit_system_conversions.py`) | `Prefix` / `BaseUnit` / `Unit` named tuples; `SI_PREFIXES`, `SI_BASE_UNITS`, `SI_DERIVED_UNITS`, `VERY_COMMON_UNITS`, `COMMON_UNITS`, `IMPERIAL_UNITS` (ordered tuples); `UNIT_SETS`, `units_in`, `CONVERSION_TO_BASE_SI` |
| `params.py` | `QuantityParams(ExpressionParams)`: `strictness`, `legacy_preprocessing`, `unit_sets`; `from_dict` maps `"legacy"` and `units_string` |
| `tags.py` | `QuantityTag`: `UNIT`, `NON_UNIT`, `NUMBER`, `REJECTED_UNIT` (was `U`/`V`/`N`/`R`) |
| `parser.py` | Unit dictionaries, tag handler, natural juxtaposition, `build_quantity_parser` (cached per unit sets and strictness) |
| `quantity.py` | `PhysicalQuantity`, `parse_quantity`, `RevertedUnit` |
| `preprocessing.py` | `preprocess_quantity(expr, params, *, name=None)` → `str`, `preprocess_legacy` (string searches built once, deprecated), `transform_prefixes_to_standard` |
| `errors.py` | `QuantityError` (a `ValueError`) → `QuantityParseError`, `UnitConversionError` |

`preview.py` (`preview_function`, `fix_exponents`) was removed in 0.3.0 and moved to compareExpressions — see above.

**Deviations from the plan:**
- `R` became `REJECTED_UNIT`: units written next to each other in strict mode, which strict syntax doesn't accept as a unit.
- `preprocess_quantity` has the same shape as `preprocess_expression` (`(expr, params, *, name=None) -> str`): compareExpressions uses both interchangeably as a context's preprocessing hook.
- `PhysicalQuantity` stays a regular class (its constructor computes everything, as before, so errors surface at the same point). compareExpressions reads its attributes, so only the awkward names changed (`*_latex_string` → `*_latex`, `converted_unit_factor` → `unit_factor`, `parsing_params` → `parsing_config`, `parameters` → `params`).

## Checklist

### Bugs (regression test, one commit each)

- [x] Litre's plurals were one string, so `2 litres` parsed as litre·second (12 parity probes).
- [x] `(2 m) s` raised `IndexError` in every mode: rotating into a group made a cycle. Groups are atomic now (20 probes; they read like `(2 m)` alone).
- [x] `fix_exponents` skipped `**` twice: `m**{-2}` → `m**(2)`, so the preview turned N·m⁻² into N·m². **Also found:** an unbraced exponent borrowed the next brace anywhere in the string.
- [x] Strictness defaults differed between the parser and the tag handler, and legacy matched neither. The parser's handler is now the single source (changes the 4 legacy `3 µs` probes).
- [x] `max_unit_name_length` counted keys, not characters (perf).
- [x] The preview passed raw params to `parse_expression` and mutated `params["is_latex"]` (fixed when porting to the typed expression_parsing API in Phase 3).
- [x] `node.label in "SPACE"` substring test → `==`.
- [x] **Found during the refactor:** `5 m/s x` (a unit between value parts) rotated back and forth until `RecursionError`; it now raises `QuantityParseError`. The first port turned this into an infinite loop, which the parity run caught before commit.
- [x] **Found during the refactor:** the LaTeX preview of a unit alone printed the missing value as `None` (`Nonekilogram`).

### Restructure / API

- [x] Positional `x[0]..x[4]` indexing replaced by named fields everywhere; the tables were verified equal to v0.1's and the 1600 SI conversions identical.
- [x] Deterministic (table-order) iteration instead of set order. Legacy rewrites were checked to be independent of alternation order.
- [x] Valid-unit sets computed by one helper (`_unsplittable_names(..., all_forms=)`) for both uses.
- [x] Module-level `temp_dict`, the identity-lambda `tag_handler` default and the `CONSIDER` comment removed.
- [x] Bare `Exception`s → `QuantityParseError` / `UnitConversionError`; the preview no longer relabels quantity parse errors as "Failed to parse LaTeX expression".

### Types & lint

- [x] mypy with typed definitions required; ruff lint and format.

### Tests (284 → 315)

- [x] `test_regressions.py`, `test_api.py`; carried-over suites ported (and no longer mutate the shared `default_parameters` fixture).
