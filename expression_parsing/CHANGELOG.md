# Changelog: lambdafeedback-expression-parsing

## 0.3.0 (unreleased)

Further tidy-up after the 0.2.0 extraction: previewing a response and mapping failures to learner-facing feedback text are app-layer concerns, so they move out of this package.

### Breaking

- `preview_function`, `parse_symbolic`, `Preview`, `Result`, `ExpressionSyntaxError`, `FeedbackTag` and `FeedbackTagName` have moved out of this package entirely, to compareExpressions: rendering a response as LaTeX/SymPy, and mapping a tag to feedback text, are app-layer display concerns, not expression parsing.
- `preprocess_expression`, `convert_bracket_notation` and `convert_absolute_notation` now return a plain `str` (raising instead of returning `Preprocessed`/a `(str, FeedbackTag | None)` tuple). The `Preprocessed` dataclass is gone. `BracketNotationError` and `AbsoluteValueNotationError` (both `ExpressionParsingError`) are raised on failure; each carries the best-guess rewrite as `.expression`, so a caller can catch it, decide whether to continue with the guess (adding non-fatal feedback) or propagate, exactly as `compareExpressions` already did per-context (learner response vs. answer/criteria).
- `convert_bracket_notation` now computes a best-guess rewrite even on a bracket-kind mismatch (e.g. `[x+y)` guesses `(x+y)`), instead of leaving the expression untouched. This often recovers a wrong-*kind* mismatch outright; a genuinely unbalanced expression still fails downstream.
- Every exception in `errors.py` now carries structured fields instead of only a message: `UnknownConventionError.convention`, `SymbolAssumptionError.text`/`.symbol`/`.assumption`, `LatexParseError.symbol`/`.expression`/`.response`/`.wrapper`, `ExpressionParsingError.expression` (the base, used by generic parse failures). The duplicated "Unknown convention" check (`conventions.py` and `params.py`) is now one `validate_convention` helper.
- `PATTERNS` and `SyntacticalPattern` have moved out to compareExpressions: their summaries are learner-facing feedback text built from criteria nodes. The matchers stay here: `is_number`, and the now-exported `is_complex_number_on_cartesian_form` and `is_complex_number_on_exponential_form`.
- `parse_expression` only evaluates mathematics (see Security). An input that relied on other SymPy names now reads them as plain symbols or undefined functions (e.g. `plot(x)`), and Python builtins other than `abs`/`max`/`min` are unavailable.
- `parse_expression` and `apply_convention` raise `ExpressionParsingError` for every invalid input. Tokenizer errors, `SyntaxError`, slr_parsing's `ParseError` and evaluation errors used to escape unwrapped; they are now its `__cause__`.
- `ExpressionParams` checks parameter types and raises the new `InvalidParameterError` (`.name` is the field): booleans must be booleans (`"false"` was kept as a truthy string), and lists of strings must be lists (`"aliases": "xy"` used to become the aliases `x` and `y`). `ExpressionParams.symbols` is now a read-only mapping.
- `BracketNotationError(expression, *, original)`: the message now quotes the expression as written (`.original`), not the rewrite.
- `convert_absolute_notation` raises `AbsoluteValueNotationError` for an unpaired `|` (e.g. `x|`, which became the unbalanced `x)`).
- The unused `params.as_params` helper is removed.
- Python keywords are read like any other name, at the token level, instead of by text substitution: `in`, `is`, `if`, `True`, ... become `i*n`, `i*s`, ... (or a single symbol with `strict_syntax`) where they used to raise. This replaces the `as` → `a*s` rule, which was a plain substring replacement and so also rewrote longer names: with `strict_syntax`, `phase` became `pha*se`. With `strict_syntax` a lone `as` is now the symbol `as`, like any other multi-letter name.
- With `elementary_functions`, the short function spellings `re`, `im`, `int`, `arg`, `sum`, `sign`, `min`, `max` and `sec` (any case; `EMBEDDABLE_FUNCTION_NAMES` in `symbol_tables`) are only functions when followed by `(`, `^` or `**`; anywhere else, including on their own, they are letters. They used to match inside ordinary words, so `area`, `time`, `rest`, `interval`, `pressure` and `design` failed to parse (`a re a`, `t im e`, `int Erval`). Consequently a bare `max` or `re` now parses as letters instead of failing. Other function names (`sin`, `cos`, `tan`, `log`, ...) are unchanged.
- A function name without bracketed arguments (`sin`, `sin x`, `sqrtx`, a declared function `f x`) raises `ExpressionParsingError` saying so ("sin is a function, so its argument needs brackets: sin(...)") instead of "Failed to parse Sympy expression" or "Invalid syntax". What parses is unchanged.
- Arithmetic on a bracketed list, such as an unrecognised function's arguments (`xmax(a, b)` or `int(x, x)` without `elementary_functions`), is reported as such and suggests checking the function name. It used to say "Arithmetic on a set ({...}) is not supported", though no set was written. Sets (`{x+1}*{x-1}` with `strict_syntax`) keep that message.
- The two sides of an equation are parsed like a whole expression: unevaluated, or simplified with `simplify` (which equations used to ignore). They used to be evaluated, so `x+x=2` gave `Eq(2*x, 2)` where `x+x` gave `x + x`, and `9**9**9=x` never finished: any learner could stall an evaluation. Now `x+x=2` gives `Eq(x + x, 2)`.
- Defining both a `lambda` and a `lamda` symbol raises `InvalidParameterError` (they are the same symbol; the `lamda` definition was silently dropped).

### Security

- **`parse_expression` no longer evaluates arbitrary Python.** SymPy's `parse_expr` `eval`s the transformed input, and its default namespace includes Python's builtin functions: a learner response such as `open('/etc/hosts')` was executed (it only failed afterwards, as not a SymPy expression), and `__import__(...)` and attribute access were reachable. Parsing now goes through `_safe_parse.safe_parse_expr`: the generated code is checked against an allowlist of syntax (arithmetic, comparisons, calls of plain names, numbers; a string only as the name in `Symbol('x')`/`Function('f')` or the digits in `Float('1.5')`/`Rational`/`Integer`/`Number`, since SymPy `sympify`s string arguments with its unrestricted namespace), then evaluated with SymPy's mathematical names only and no builtins. `parse_latex` parses symbol aliases the same way (they were evaluated with builtins too). compareExpressions, where this code came from, has the same exposure.

### Fixed

- `is_complex_number_on_exponential_form` took exponential time on inputs like `2*exp(` followed by a run of digits (26 digits took over 10 s), which a learner's response could trigger through "written as" criteria. `NUMBER_REGEX` and `NONNEGATIVE_NUMBER_REGEX` could match an empty string after a digit, and the check repeated them; they now never match empty (they accept the same numbers), and the complex-form checks match each number atomically. `is_complex_number_on_cartesian_form` no longer accepts an empty string or a lone `+`, and both checks no longer accept numbers run together (`5E7e7`, `exp04I`). `generate_arbitrary_number_pattern_matcher` matches each number atomically too: a pattern whose numbers are separated only by spaces (`1 2 3`) took polynomial time on a long run of digits (1000 digits: over 8 s), and matched a single number (`3`) through the empty-match bug.
- A symbol code that merely contains `lambda` (e.g. `lambda_1`) keeps its name. Every substitution's replacement had `lambda` rewritten to `lamda`, so `lambda_1` became `lamda_1`, which was then split as `lamda*_1` and lost its LaTeX.
- A task symbol whose code is a Python keyword (`in` for inches, `del`, `as`, ...) parses as that symbol, keeping its LaTeX and assumptions; it used to raise (or, for `as`, become `a*s`).
- `sympy_to_latex` prints symbols that have assumptions (from `symbol_assumptions`) with the task's LaTeX. The printer matched symbols by equality, and `Symbol('x', positive=True)` is not `Symbol('x')`.
- `{f(x,y), 2}` is two answers, `f(x,y)` and `2`: `create_expression_set` split at every comma, including those inside brackets.
- `is_number("2*10^3")` is true: the `^` in `NUMBER_REGEX` was an unescaped anchor, so the `*10^` exponent form never matched.
- `compute_relative_tolerance_from_significant_decimals` counts only the mantissa for `1.5E3` and `1.5*10^3` (it counted the exponent's digits as significant figures, giving 5e-4 instead of 0.05).
- `parse_latex` recognises `\pm`/`\mp` without a following space (`1\pm\sqrt{2}` failed to parse), and no longer runs symbol substitution over the LaTeX when expanding them (`\lambda` became `\lamda`).

## 0.2.0 (unreleased)

The first release after the extraction refactor. The import path is now `lambdafeedback.expression_parsing` (was `expression_parsing`).

### Renamed and restructured

Parameters are typed now. Build an `ExpressionParams` with `ExpressionParams.from_dict(evaluation_params)` (JSON keys such as `complexNumbers` are mapped, unrelated keys ignored). It is immutable, and its `symbols` are normalised on construction: blank codes and aliases are dropped, aliases stripped, and `lambda` moved to `lamda`, which always exists. `SympyParsingConfig` replaces the `parsing_params` dict. `preview_function` still accepts a plain parameter mapping.

| v0.1 | 0.2.0 |
|---|---|
| `expression_parsing` (import) | `lambdafeedback.expression_parsing` |
| `default_parameters` (dict) | `ExpressionParams()` defaults |
| `params` dicts passed to `substitute_input_symbols`, `create_expression_set`, `preprocess_expression` | `ExpressionParams` |
| `create_sympy_parsing_params(params, unsplittable_symbols, symbol_assumptions)` → dict | `SympyParsingConfig.from_params(params, unsplittable_symbols, symbol_assumptions)`; variants via `.replace(...)` |
| `parse_expression(expr, parsing_params)` | `parse_expression(expr, config)`. It still doesn't substitute symbol aliases: run `preprocess_expression` first. |
| `preprocess_expression(...)` → `(success, expr, feedback)` | → `Preprocessed(expression, feedback)` with `.success` |
| `convert_bracket_notation` / `convert_absolute_notation` → `(expr, (tag, FeedbackTag))` | → `(expr, FeedbackTag \| None)` |
| `FeedbackTag` namedtuple | frozen dataclass `FeedbackTag(tag, inputs)`; tag names in the `FeedbackTagName` `StrEnum` |
| `parse_symbolic` raised `SyntaxError(FeedbackTag(...))` | raises `ExpressionSyntaxError`; the tag is `.feedback` |
| `preview_function` raised `ValueError` | raises `ExpressionParsingError` (a `ValueError`) |
| `parse_latex(response, symbols, simplify, parameters=None)` | `parse_latex(response, symbols, simplify=False)`; `symbols` maps codes to `SymbolSpec` |
| `sympy_to_latex(expr, symbols_dict, settings)` | `sympy_to_latex(expr, params.symbols, settings)` |
| symbol dicts `{"latex": ..., "aliases": [...]}` / `SymbolDict` / `SymbolData` | `SymbolSpec(latex, aliases)`; `from_dict` accepts the dict form |
| `Params` TypedDict | removed: pass a mapping or `ExpressionParams` |
| `Preview` / `Result` TypedDicts | same names; `feedback` is `NotRequired` (lf_toolkit's `Preview` requires it) |
| `SLR_implicit_multiplication_convention_parser(convention)` | `convention_parser(convention)` (cached per convention) |
| `preprocess_according_to_chosen_convention(expr, params)` | `apply_convention(expr, convention)` |
| `transform_unicode_greek_symbols` / `protect_elementary_functions_substitutions` / `convert_unicode_dashes` | `substitution.greek_symbol_substitutions` / `elementary_function_substitutions` / `unicode_dash_substitutions` |
| `elementary_functions_names` / `special_symbols_names` (lists mutated at import) | `symbol_tables.ELEMENTARY_FUNCTIONS` / `GREEK_SYMBOLS` (tuples of `SymbolAliases`) |
| `is_number_regex` / `is_nonnegative_number_regex` | `numbers.NUMBER_REGEX` / `NONNEGATIVE_NUMBER_REGEX` |
| `patterns` (dict of dicts) | `PATTERNS` (dict of `SyntacticalPattern`) |
| `ModifiedLatexPrinter`, `symbol_latex_re` | private `_LatexPrinter`; `latex.SYMBOL_LATEX_RE` |

Modules: `params`, `symbol_tables`, `preprocessing`, `substitution`, `conventions`, `sympy_parsing`, `latex`, `preview`, `numbers`, `feedback`, `errors` (replacing `expression_utilities`, `preview_utilities`, `symbolic_preview` and `syntactical_comparison`). The `typing_extensions` dependency is dropped.

Behaviour changes from normalising symbols once: every code path now sees the task's `lambda` symbol as `lamda`, printed with the task's LaTeX (direct `parse_expression` + `sympy_to_latex` used to fall back to `\lambda`, and the LaTeX preview output `lambda`), and `lamda` is always an unsplittable symbol.

Also: the implicit-multiplication convention parser is built once per convention instead of on every parse, and `create_expression_set` returns its expressions in first-seen order (it used to be set order, which depends on the hash seed); substitution precedence ties are broken deterministically.

### Security

- **`symbol_assumptions` is no longer evaluated as code.** The parameter string (e.g. `"('a','positive') ('f','function')"`) was passed to `eval()`, and each assumption was pasted into another `eval("Symbol('x', <assumption>=True)")`, so a task author (or anyone who could set evaluation parameters) could run arbitrary Python. Groups are now read with `ast.literal_eval` and must be pairs of strings; assumption names must be identifiers and are passed as `Symbol(name, **{assumption: True})`. Malformed input raises `SymbolAssumptionError` (a `ValueError`). Valid assumptions behave as before, including `constant` and `function`.

### Fixed

- Inputs such as `2E` or `xE` parse (fixed in `slr_parsing`: the implicit-multiplication convention parser scanned a capital `E` as its grammar symbol).
- `parse_expression("a=b=c")` raises `ExpressionParsingError` instead of silently returning `Eq(a, b)` (everything after the second `=` was dropped).
- With `strict_syntax`, arithmetic on `{}` set literals (e.g. `{x+1}*{x-1}`) raises `ExpressionParsingError`. It used to build `Mul(FiniteSet, FiniteSet)`, which SymPy deprecates (the `SymPyDeprecationWarning` noted in `NOTES.md`) and will reject in a future version.
- `create_sympy_parsing_params` fills in missing parameters from the defaults instead of raising `KeyError` (e.g. for `complexNumbers`) when the caller hasn't merged `default_parameters` first.
- `preview_function` works when a symbol is defined without `latex` (e.g. `{"bc": {"aliases": ["bc"]}}`). It raised `KeyError: 'latex'`, so compareExpressions showed the raw response instead of its LaTeX. (Found while adopting the packages in compareExpressions.)
- `create_expression_set` no longer raises `IndexError` when an expression is only `plus_minus` (± with nothing after it).
- A user-defined `lambda` symbol keeps its LaTeX and aliases. `substitute_input_symbols` renames `lambda` to `lamda` inside `params["symbols"]`, and a second call (the preview makes several) replaced the renamed symbol with the default one, so previews showed `\lambda` instead of the task's LaTeX and custom aliases stopped working.
- Symbol aliases are stripped and blank aliases dropped as intended. The `.strip()` result was discarded, and blank aliases were deleted by index while the list shrank, which removed real aliases (e.g. `["", "", "xx"]` lost `"xx"`). The same cleanup for the legacy `input_symbols` format is fixed too; it could raise `IndexError` on an empty entry.
- `preview_function` and `parse_latex` no longer modify the caller's parameters (they merged in defaults, set `rationalise`, and normalised `symbols` in place), and `sympy_to_latex` no longer adds its default settings to the caller's `settings` dict.
- `parse_latex` no longer prints alias parse errors to stdout (an alias that isn't an expression is still used as a plain symbol name), and raises `LatexParseError` (a `ValueError`) with a single message. It used to raise `ValueError("Failed to pass expression during preview: ", str(e))`, whose message was a tuple.
- `sanitise_latex` raises `LatexParseError` for an unclosed `\mathrm{` / `\text{` instead of looping forever (the scan restarted from the beginning). units' LaTeX preview runs it on learner input, so a malformed response would hang the evaluation.
- `parse_latex` splits a top-level `=` itself and returns `Eq(lhs, rhs)`, rejecting more than one `=`. The PyPI release of latex2sympy2 (this package's dependency) reads `x = 2` as an *assignment*: it returns `2` and stores `x` in module-global state. The lambda-feedback fork that compareExpressions uses returns `Eq(x, 2)`, and results now match that on either build. (This package depends on PyPI latex2sympy2 so that it stays publishable.)
