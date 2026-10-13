# Changelog: lambdafeedback-units

## 0.3.0 (unreleased; pre-release 0.3.0rc2, tag v0.3.0-rc.2)

The first public release. This is a further tidy-up after the 0.2.0 extraction: the package now only does unit conversion. Package metadata (MIT licence, README, URLs) is in place for PyPI. Python 3.13 and later is supported, now that `lambdafeedback-expression-parsing` no longer depends on latex2sympy2. SymPy 1.14 or later is required (was 1.12): 1.12 predates Python 3.12, and a configuration with a declared function (`symbol_assumptions` `function`) can only be pickled from 1.14.

### Breaking

- Requires Python 3.12 or later (3.11 is not supported).
- `PhysicalQuantity.standard_values` is a tuple of expressions (several for a value such as `{1, 2}`), replacing `standard_value`, which was one expression or a set.

- `preprocess_quantity(expr, params, *, name=None)`, the same shape as `expression_parsing.preprocess_expression`.
- `∙` (bullet operator) is a product sign, like `·`, `⋅` and `×` (as in expression parsing).
- Unit LaTeX drops the brackets around a whole numerator, denominator or exponent, which the fraction or superscript already groups: `kg/(m s)` gives `\frac{\mathrm{kilogram}}{\mathrm{metre}~\mathrm{second}}` (was `\frac{\mathrm{kilogram}}{(\mathrm{metre}~\mathrm{second})}`).

- A unit spelled out from a unit set that isn't selected raises the new `DisallowedUnitError` (a `QuantityParseError`, with `.unit` and `.unit_sets`): with only `SI`, `10 litre`, `3 feet` and `5 °` are rejected, naming the set that has the unit. Before, most were read as letters in the value, so `10 litre` was `10*E*i*l*r*t` with no unit (the `e` read as Euler's number), and a few raised an unrelated error. Names, alternative spellings and plurals are checked, with or without a prefix; symbols (`L`, `h`) are still read as variables.
- **Angles are in radians.** The radian and the steradian are now 1, and the degree is `pi/180`. Before, the radian was `1/(2*pi)`, the steradian `1/(4*pi)` and the degree `1/360` (fractions of a turn), while the arcminute and the arcsecond were already in radians, so `60 angleminute` didn't equal `1 degree`. This changes `standard_value`, `unit_factor`, `expanded_unit` and `dimension` for every angle unit.
- `parse_quantity` raises only `QuantityError`s. A parser error (`slr_parsing.ParseError`/`ScanError`, e.g. for `2 m)`) and a value SymPy can't parse (`ExpressionParsingError`, e.g. `2 x;y`) are now raised as `QuantityParseError`, with the original error as `__cause__`. Every `QuantityError` carries `expression` and `name`.
- `QuantityParams` validates `unit_sets`: an unknown name (such as `"si"`) raises `QuantityParamsError`. Before, it was silently ignored, and no units were recognised. `from_dict` splits `units_string` on spaces and commas instead of testing for substrings, so `"SIcommon"` is rejected rather than read as both sets.
- An unknown `strictness` raises `QuantityParamsError` (with `.field`). It is still an `ExpressionParsingError`, so existing handlers keep working.
- `UNIT_SETS` and `CONVERSION_TO_BASE_SI` are read-only mappings (`MappingProxyType`). Assigning to them raises `TypeError`, where before it would have silently changed every cached parser.
- `parse_quantity` and `preprocess_quantity` now take `QuantityParams` only; the `Mapping[str, Any]` (raw dict) fallback is gone, along with the `as_quantity_params` helper. Convert evaluation-function parameters explicitly at the call site with `QuantityParams.from_dict(evaluation_params)`.
- `preview_function` and `fix_exponents` have moved out of this package entirely, to compareExpressions (`app/context/physical_quantity_preview.py`): building a LaTeX/SymPy preview string is an app-layer display concern, not unit conversion. Import them from there instead of `lambdafeedback.units`.
- `preprocess_quantity` now returns a plain `str` (`expression_parsing.preprocess_expression`, which it matches the shape of, no longer returns `Preprocessed`).
- `FeedbackTag` is removed, matching `expression_parsing`'s move from feedback tags to typed exceptions: mapping a parsing fact to feedback text is an app-layer concern, not this package's. `PhysicalQuantity.messages` (`(message_id, FeedbackTag)` pairs) is replaced by `PhysicalQuantity.reverted_units: list[RevertedUnit]` — plain `before`/`marked`/`after` facts about unit-like text found inside a value, with no tag name or synthetic id. This isn't a raised exception (unlike `expression_parsing`'s failures): it's non-fatal and can fire multiple times per response, so it stays a collected list.
- `PhysicalQuantity.value_latex` no longer calls `expression_parsing.preview_function` (removed): it builds the LaTeX directly from `preprocess_expression` + `parse_expression` + `sympy_to_latex`, catching `BracketNotationError`/`AbsoluteValueNotationError` to preview with the best-guess rewrite rather than failing outright (matching the old behaviour of ignoring preprocessing feedback).
- Requires `lambdafeedback-expression-parsing` 0.3.0 or later.

### Added

- DEBUG logging through module loggers (`lambdafeedback.units.*`), with a `NullHandler` on the package logger; nothing is logged at INFO or above. See the repository README. `parse_quantity` logs the normalised text and the value/unit split.
- `DisallowedUnitError` (see Breaking).
- `PhysicalQuantity.base_dimension`: the dimension without the unit's factor (`5 km/h` gives `length/time`, where `dimension` is `10**3*length/((3600*time))`), and `same_dimension(a, b)` to compare two quantities' dimensions.
- `MAX_INPUT_LENGTH` (10,000 characters): `parse_quantity` raises `QuantityParseError` for longer input, and `preprocess_quantity` returns it unchanged. This bounds the running time on any input.
- `MAX_LEGACY_LENGTH` (1,000 characters): the deprecated legacy rewrites are skipped for longer input.
- `QuantityParamsError`, `AnyUnit` and `__version__` are exported.
- `PhysicalQuantity` declares typed attributes (SymPy `Basic` for the SI forms) and has a readable `repr`, e.g. `PhysicalQuantity(value='5', unit='kilometre/hour')`.
- `README.md` documents usage, parameters, unit sets, errors and known limitations.

### Fixed

- The roentgen was converted as kelvin per kilogram; it is 2.58×10⁻⁴ C/kg (ampere·second per kilogram).
- The imperial pint was 0.00056826 m³; it is 0.00056826125 m³, so that 8 pints make a gallon.
- `nautical_miles` is recognised as the plural of `nautical_mile`. Before, only `nauticalmiles` was, and in natural mode `2 nautical_miles` parsed as 2 nautical_mile·second.
- The comment in `data.py` said the symbols of `COMMON_UNITS` were not accepted. They always have been, and the docs now say so.
- The value's LaTeX preview no longer splits a function call that contains unit symbols. `sin(2)` was previewed as `s \cdot in \cdot 2` and `sqrt(11)` as `\frac{1}{s} \cdot q \cdot r \cdot t \cdot 11`, while the value itself was parsed as the function call. The preview now matches the value.
- A number inside the unit raises `QuantityParseError` ("Cannot separate the value from the unit"). Before, `2 m 3 s` gave the unit `metre 3 second`, with dimension `length*3*time`, and `1 hour 30 minutes` gave a dimension of time². Numbers in exponents (`m^2`) and the `1` of `1/s` are still accepted.
- `°C`, `°F`, `deg C`, `℃` and `℉` raise `QuantityParseError` (temperatures are in kelvin only). Before, `2 °C` was read as 2 degree·coulomb.
- `Ω` is recognised as the ohm's symbol in both modes, with prefixes (`2 kΩ`, `2 MΩ`). Before, strict mode only accepted `O`, and the only prefixed form in either mode was `kO`. `O` still works.
- Any whitespace between value and unit is a separator, including tabs, newlines, no-break and thin spaces, and zero-width characters are ignored. Before, `2\xa0m` (pasted with a no-break space) was the value `2\xa0m` with no unit.
- Natural mode scans a long run of letters in linear time. It tried every prefix of the rest of the word at each position, which is cubic, so 5000 letters took minutes.
- Input nested too deeply for the recursive steps (thousands of operators, such as `m*m*…*m`) raises `QuantityParseError`. Before, `RecursionError` escaped.
- `PhysicalQuantity` leaves its parser out when pickled or deep-copied, and rebuilds it from the cache. The parser holds closures, so pickling always failed. This needs `lambdafeedback-expression-parsing` with picklable `ExpressionParams`.
- `QuantityParamsError` can be unpickled. It used to raise `TypeError`, because unpickling called it with one argument instead of two.
- A number with a huge exponent or too many digits (`1e999999 m`) raises `QuantityParseError` at once. It hung: the value's preview parses without rationalising, and SymPy took minutes to build the float. The limits (1000 digits, exponent ±1000) are `lambdafeedback-expression-parsing`'s.
- Legacy preprocessing searches on from each rewrite instead of restarting from the beginning of the input (same output). The rewrites themselves can still take time cubic in the length (`"μ " * 400` needs 80,000 of them), hence `MAX_LEGACY_LENGTH`; `"μ " * 20000` took hours and is now passed through at once.
- The `marked` text of `reverted_units` is built from each node's children's text, computed once, instead of walking each unit's subtree again (same output). A value with a long chain of units took quadratic time: `"x m " * 2500` took 14 s and now takes under a second.
- A unit's exponent must be numbers (combined with brackets, `*`, `/`), within ±`MAX_UNIT_EXPONENT` (100); otherwise `QuantityParseError`. `km^Pa^km` (a unit as an exponent) hung, computing about 1000^(1000^1000), and `2 km^99999999` hung computing its factor; `km^Pa` was accepted as a unit, and `2 km^1000` failed with an unrelated digit-limit error. `2 m^99999999`, which used to parse, is rejected too.
- `·`, `⋅` and `×` are read as `*`, so `2 kg·m` and `2×10^3 m` parse. Before, they raised errors.
- With `is_latex=True`, LaTeX spacing (`~`, `\,`, `\ `, `\quad`) and upright text (`\mathrm{m}`, `\text{m}`) are read as plain spaces and text. Before, MathLive's `2~\mathrm{m}` raised an error, and `2~m` was read as the value `2*m` with no unit.

### Changed

- The regular expressions in preprocessing and parsing are replaced by string scanners, with the same results. The quantity grammar's tokens are `slr_parsing.Lexeme`s (requires `lambdafeedback-slr-parsing` with literal token patterns).

### Deprecated

- `strictness="legacy"` (and constructing `QuantityParams(legacy_preprocessing=True)` directly) now emits a `DeprecationWarning`, and will be removed in 1.0. The behaviour is unchanged (natural strictness with the old `legacy` preprocessing rewrites), but new callers should use `strictness="natural"` (the default).

## 0.2.0 (internal, not published)

The first release after the extraction refactor. The import path is now `lambdafeedback.units` (was `units`).

### Renamed and restructured

Parameters are typed now. `QuantityParams` extends `expression_parsing.ExpressionParams` with `strictness`, `legacy_preprocessing` and `unit_sets`, and `QuantityParams.from_dict(evaluation_params)` maps `strictness: "legacy"` and `units_string`. Parsers are built once per `(unit_sets, strictness)` and cached.

| v0.1 | 0.2.0 |
|---|---|
| `units` (import) | `lambdafeedback.units` |
| `SLR_quantity_parser(params)` + `SLR_quantity_parsing(expr, params, parser, name)` | `parse_quantity(expr, params, name="response")` (parser cached internally; `build_quantity_parser(unit_sets, strictness)` if you need it) |
| `PhysicalQuantity(name, parameters, ast_root, parser, messages, tag_handler)` | created by `parse_quantity` |
| `quantity.value_latex_string` / `unit_latex_string` / `latex_string` | `quantity.value_latex` / `unit_latex` / `latex` |
| `quantity.converted_unit_factor` | `quantity.unit_factor` |
| `quantity.parsing_params` (dict) | `quantity.parsing_config` (`SympyParsingConfig`) |
| `quantity.parameters` (dict) | `quantity.params` (`QuantityParams`) |
| `expression_preprocess(name, expr, params)` → `(True, expr, None)` | `preprocess_quantity(name, expr, params)` → `Preprocessed` (same shape as `expression_parsing.preprocess_expression`) |
| `params["strictness"] == "legacy"` | `QuantityParams(strictness="natural", legacy_preprocessing=True)`; `from_dict` maps `"legacy"` |
| `params["units_string"]` (substring test) | `QuantityParams.unit_sets` (frozenset); `from_dict` maps `units_string` the same way |
| `QuantityTags.U` / `V` / `N` / `R` | `QuantityTag.UNIT` / `NON_UNIT` / `NUMBER` / `REJECTED_UNIT` |
| `set_of_SI_prefixes` / `set_of_SI_base_unit_dimensions` / `set_of_derived_SI_units_in_SI_base_units` / `set_of_very_common_units_in_SI` / `set_of_common_units_in_SI` / `set_of_imperial_units` (sets of positional tuples) | `SI_PREFIXES` / `SI_BASE_UNITS` / `SI_DERIVED_UNITS` / `VERY_COMMON_UNITS` / `COMMON_UNITS` / `IMPERIAL_UNITS`: ordered tuples of `Prefix(name, symbol, factor, alternatives)`, `BaseUnit(name, symbol, dimension, alternatives, plurals)` and `Unit(name, symbol, si_expansion, alternatives, plurals)` |
| `units_sets_dictionary` | `UNIT_SETS`; `units_in(unit_sets)` |
| `conversion_to_base_si_units` | `CONVERSION_TO_BASE_SI` |
| `preview_function(response, params)` mutated `params` | takes `QuantityParams` or a mapping; never mutates it |
| bare `Exception`s | `QuantityParseError` / `UnitConversionError` (both `QuantityError`, a `ValueError`) |

Modules: `data` (was `unit_system_conversions`), `params`, `tags`, `parser`, `quantity`, `preprocessing`, `preview`, `errors` (replacing `physical_quantity_utilities` and `physical_quantity_preview`).

### Fixed

- `litre`'s plural forms were the single string `'litres,liters'`, so neither plural was recognised. In natural (and legacy) mode `2 litres` parsed as **2 litre·second**, with the trailing `s` read as seconds. It now parses as 2 litre.
- A bracketed value and unit followed by another unit, such as `(2 m) s` or `(2 kg) (m/s)`, no longer crashes with `IndexError` in every strictness mode. Splitting value from unit rotated the tree into the group, which only works for binary nodes: for a group it made the root and the group each other's child. Groups are now kept whole, so these read the way `(2 m)` alone already did, with the whole input as the unit and the number as a factor of it. A clear error might serve learners better; this is only a first step.
- LaTeX exponents written `**{...}` lost their first character: `fix_exponents` skipped the operator twice, so `m**{-2}` became `m**(2)` and the preview turned N·m⁻² into N·m². An unbraced exponent also borrowed the next brace anywhere in the string (`x^2y^{3}` → `x**(y^{3)`). Only a brace directly after the operator is unwrapped now.
- A unit between two value parts (e.g. `5 m/s x`) raises `QuantityParseError("Cannot separate the value from the unit ...")` instead of recursing until `RecursionError`. Splitting value from unit rotated the tree left and right alternately, each rotation undoing the last.
- Splitting value from unit re-tagged the tree with a tag handler for a different strictness than the parser's. It defaulted to strict when `strictness` was omitted (the parser defaulted to natural), and for `legacy` it matched neither mode. It now uses the parser's own rules. This changes legacy-mode `3 µs` (previously the whole input read as a unit with dimension `3*mu*time`; now read as a value, reporting `s` as a reverted unit, as natural mode's rules define. Neither reads microseconds: legacy preprocessing doesn't normalise `µ`).
- The strict unit matcher tried every length up to the *number* of known units (hundreds) at each position; it now stops at the longest unit spelling.
- The quantity preview previously passed the raw parameter dict to `parse_expression` as if it were parsing parameters; it now uses a proper parsing configuration (no output changes on the parity corpus).
- The LaTeX preview of a response that is only a unit gave SymPy output such as `Nonekilogram`: the missing value was printed as `None`. It is now just the unit.

### Known issues (unchanged from v0.1)

- `reverted_units` entries are emitted for every node carrying the unit tag, so a group that contains a unit is reported as well as the unit itself. The group's positions come from synthetic tokens, so its before/marked/after text is garbled (e.g. for `2 kg + 3`). The entry for the unit itself is correct.
- Units' LaTeX preview removes all whitespace, so a value and unit must be separated with `~` (as MathLive does): `9.81 \mathrm{m}` reads as `9.81m`.
