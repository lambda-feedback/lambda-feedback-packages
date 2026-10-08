# lambdafeedback-expression-parsing

Parse learner-written mathematical expressions (`2x^2 + |x-1|`, `a/bc`,
`x ± 1`, `{1, -1}`, …) and LaTeX (`parse_latex`) into
[SymPy](https://www.sympy.org) objects, and print them back as LaTeX. Used
by [Lambda Feedback](https://github.com/lambda-feedback) evaluation
functions such as compareExpressions.

## Installation

```bash
pip install lambdafeedback-expression-parsing
```

Python 3.11–3.12 is supported. LaTeX input uses
[latex2sympy2](https://pypi.org/project/latex2sympy2/), which pins an ANTLR
runtime that imports the `typing.io` module removed in Python 3.13.

## Quick start

```python
from lambdafeedback.expression_parsing import (
    ExpressionParams,
    SympyParsingConfig,
    parse_expression,
    preprocess_expression,
    sympy_to_latex,
)

# Evaluation-function parameters (JSON) → typed, validated parameters.
params = ExpressionParams.from_dict(
    {"elementary_functions": True, "symbols": {"v_0": {"latex": "v_0", "aliases": ["v0"]}}}
)

expr = preprocess_expression("response", "v0 sin(x) + |x|", params)  # aliases, [] / {} brackets, |x| → Abs(x)
parsed = parse_expression(expr, SympyParsingConfig.from_params(params))
latex = sympy_to_latex(parsed, params.symbols)
```

The pipeline has three steps:

1. **`ExpressionParams.from_dict`** maps JSON names (`complexNumbers`, …) to
   fields, ignores unrelated keys and checks types. A malformed parameter
   raises `InvalidParameterError`.
2. **`preprocess_expression`** substitutes symbol aliases and rewrites bracket
   and absolute-value notation into plain SymPy syntax.
3. **`parse_expression`** applies the implicit-multiplication `convention`,
   Greek letters and function names, and returns a SymPy expression. A
   response that stands for several answers (`{a, b}` or `±`) gives a `set`,
   and `a = b` gives an unevaluated `Equality`.

## Errors

Every failure raises a subclass of `ExpressionParsingError`, which is a
`ValueError`:

| Exception | Raised when |
|---|---|
| `ExpressionParsingError` | the expression isn't valid (its `.expression` is the input) |
| `InvalidParameterError` | a parameter has the wrong type (`.name`) |
| `UnknownConventionError` | `convention` isn't recognised |
| `SymbolAssumptionError` | `symbol_assumptions` is malformed |
| `LatexParseError` | LaTeX input or a symbol's LaTeX can't be parsed |
| `BracketNotationError` | brackets are mismatched, e.g. `[x+y)` |
| `AbsoluteValueNotationError` | `\|…\|` pairs are ambiguous or unpaired |

`BracketNotationError` and `AbsoluteValueNotationError` are recoverable.
`.expression` holds a best-guess rewrite, so you can keep going with it and
tell the learner what was assumed:

```python
try:
    expr = preprocess_expression("response", response, params)
except (BracketNotationError, AbsoluteValueNotationError) as e:
    expr = e.expression  # and add non-fatal feedback
```

## Security

SymPy's `parse_expr` works by turning its input into Python code and
`eval`-ing it. This package never passes input to it unchecked. The
generated code must be pure mathematics: arithmetic, comparisons, calls of
plain names, and numbers. Attribute access, subscripts, lambdas and string
literals are rejected, apart from the `Symbol('x')`/`Float('1.5')` forms
that SymPy itself generates. The code is evaluated in a namespace with
SymPy's mathematical functions and constants and no Python builtins.
SymPy's printing, plotting, code-generation and `sympify` helpers aren't
available, so names like `plot` are read as plain symbols.

Parsing isn't thread-safe: it briefly changes process-wide warning filters,
and latex2sympy2 keeps module-level state. Parse from one thread at a time
per process; one evaluation per process, as in a Lambda Feedback evaluation
function, is fine.

Expressions are parsed unevaluated, but `simplify` (and any later
evaluation, such as comparing answers) computes: `9**9**9` would then take
practically forever. Run evaluation with a time or memory limit when
handling untrusted input.

## Licence

MIT. See [LICENSE](LICENSE). The changelog, including migration notes, is
in [CHANGELOG.md](CHANGELOG.md).