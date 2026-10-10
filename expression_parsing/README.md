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

Python 3.11 and later is supported. LaTeX input uses
[latex2sympy2_extended](https://pypi.org/project/latex2sympy2-extended/).

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
   and `a = b` gives an unevaluated `Equality`. Greek letter names are
   recognised inside words, so `2pir` is 2πr (and `spin` is s·π·n). Unicode
   operators (`−`, `×`, `÷`, `x²`) are read as their ASCII forms.

## Errors

Every failure raises a subclass of `ExpressionParsingError`, which is a
`ValueError`:

| Exception | Raised when |
|---|---|
| `ExpressionParsingError` | the expression isn't valid (`.expression` is the expression at the point it failed) |
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

Parsing isn't thread-safe: it briefly changes process-wide warning
filters. Parse from one thread at a time per process; one evaluation per
process, as in a Lambda Feedback evaluation function, is fine.

Number literals are limited to 1000 digits and exponents to ±1000
(`MAX_NUMBER_DIGITS`, `MAX_NUMBER_EXPONENT`): larger ones take SymPy minutes
to read. LaTeX nested more than 10 brackets deep (`MAX_LATEX_NESTING`) is rejected: the LaTeX parser takes
exponential time in nesting depth.

Expressions are parsed unevaluated, including functions and operator
classes called by name (`factorial(10**8)`, `Pow(9, Pow(9, 9))`), but
`simplify` (and any later evaluation, such as comparing answers) computes:
`9**9**9` would then take practically forever. A caller handling untrusted
input, such as an evaluation function, must run parsing and evaluation
under a time or memory limit.

## Licence

MIT. See [LICENSE](https://github.com/lambda-feedback/lambda-feedback-packages/blob/main/expression_parsing/LICENSE). The changelog, including migration notes, is
in [CHANGELOG.md](https://github.com/lambda-feedback/lambda-feedback-packages/blob/main/expression_parsing/CHANGELOG.md).