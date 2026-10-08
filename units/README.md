# lambdafeedback-units

Parse physical quantities such as `9.81 m/s^2` or `5 kilometres/hour` into a
value and a unit, convert them to SI base units, and compare dimensions. Built
on [SymPy](https://www.sympy.org/) for
[Lambda Feedback](https://github.com/lambda-feedback) evaluation functions,
where the input is a learner's typed answer: the parser accepts natural
spellings (`metres`, `kg m/s`, `μs`) and tells you which part is the value and
which is the unit.

Originally extracted from the
[compareExpressions](https://github.com/lambda-feedback/compareExpressions)
evaluation function.

## Install

```bash
pip install lambdafeedback-units
```

Requires Python 3.11 or 3.12. Python 3.13 isn't supported yet because
`latex2sympy2`, a dependency of `lambdafeedback-expression-parsing`, needs an
old ANTLR runtime. The import root is `lambdafeedback.units`.

## Quick start

```python
from lambdafeedback.units import QuantityParams, parse_quantity

q = parse_quantity("5 km/h", QuantityParams())
q  # PhysicalQuantity(value='5', unit='kilometre/hour')
q.value.content_string()  # '5'
q.unit.content_string()  # 'kilometre/hour'   (symbols become unit names)
q.standard_value  # 5*5/18             (SymPy, unevaluated; .simplify() → 25/18)
q.standard_unit  # metre/second
q.unit_factor  # 5/18
q.latex  # 5~\frac{\mathrm{kilometre}}{\mathrm{hour}}

parse_quantity("9.81 m/s^2", QuantityParams()).dimension  # length/time**2
```

Either part may be missing: `parse_quantity("kg", ...)` has `value is None`, and
`parse_quantity("2x", ...)` has `unit is None`.

### What a `PhysicalQuantity` holds

| Attribute | Meaning |
|---|---|
| `value`, `unit` | The value and unit parse trees (`ExprNode`), or `None`. `content_string()` gives the normalised text. |
| `standard_value` | The value with the unit's factor applied, as a SymPy expression, so it is the quantity's magnitude in SI base units. |
| `standard_unit` | The unit in SI base units, without its numeric factor. |
| `expanded_unit` | The unit in SI base units, with its factor. |
| `unit_factor` | The factor between the unit and SI base units. |
| `dimension` | The unit in terms of `length`, `mass`, `time`, `electric_current`, `temperature`, `amount_of_substance` and `luminous_intensity`. It keeps the unit's factor (`km/h` gives `5*length/(18*time)`), so compare dimensions with that factor removed. |
| `value_latex`, `unit_latex`, `latex` | LaTeX previews. |
| `reverted_units` | `RevertedUnit(before, marked, after)` records for unit-like text that was read as part of the value (e.g. `kg` in `2 kg + 3`). |

Mass is in **grams**, so that SI prefixes apply uniformly: `kilogram` expands
to `1000*gram`. Angles are dimensionless, with the radian equal to 1.

## Parameters

`QuantityParams` is a frozen dataclass. It extends
`lambdafeedback.expression_parsing.ExpressionParams`, so it also takes the
expression options (`complex_numbers`, `symbols`, `strict_syntax`, ...).

| Field | Default | Meaning |
|---|---|---|
| `strictness` | `"natural"` | `"strict"`: only unit names and symbols, separated by `*`, `/` or spaces. `"natural"` also accepts alternative spellings (`meter`, `Ω`) and plurals (`metres`), and units written together (`kgm`). |
| `unit_sets` | `{"SI", "common", "imperial"}` | Which sets of units are recognised (see below). |

```python
parse_quantity("2 metres", QuantityParams(strictness="strict"))  # value='2 metres', unit=None
parse_quantity("2 metres", QuantityParams())  # value='2', unit='metre'
parse_quantity("2 ft", QuantityParams(unit_sets={"SI"}))  # value='2 ft', unit=None
```

To build parameters from an evaluation function's JSON parameters, use
`QuantityParams.from_dict`. It also reads `units_string`, the unit-set names
separated by spaces or commas:

```python
params = QuantityParams.from_dict({"strictness": "strict", "units_string": "SI imperial"})
```

An invalid value raises `QuantityParamsError`, which is also an
`ExpressionParsingError`. `strictness: "legacy"` still works but emits a
`DeprecationWarning`, and will be removed in 1.0.

## Units

The tables are in `lambdafeedback.units` as tuples of named tuples:
`SI_PREFIXES`, `SI_BASE_UNITS`, `SI_DERIVED_UNITS`, `VERY_COMMON_UNITS`,
`COMMON_UNITS` and `IMPERIAL_UNITS`. `UNIT_SETS` maps each set name to its
units, and `CONVERSION_TO_BASE_SI` maps every (prefixed) unit name to its SI
expansion. Both are read-only.

| Set | Contents |
|---|---|
| `SI` | The 7 base units (with the gram for mass) and 19 named derived units (hertz to katal; degree Celsius is left out). Every SI prefix from quecto to quetta can be attached. |
| `common` | `SI`, plus the radian, the steradian and accepted non-SI units: minute, hour, day, litre, tonne, degree, electronvolt, ångström, bar, and others. |
| `imperial` | inch, foot, yard, mile, fluid ounce, gill, pint, quart, gallon, ounce, pound, stone. |

Some symbols differ from the SI ones, to avoid collisions: `r` is the radian
(`rad` is the radiation-dose unit), and `O` is the ohm (`Ω` is accepted in
natural mode).

## Errors

All errors derive from `QuantityError`, which is a `ValueError`, and carry
`expression` (the input) and `name` (e.g. `"response"`):

| Exception | Raised when |
|---|---|
| `QuantityParseError` | The input can't be read as a quantity: unbalanced brackets, a dangling operator, a unit between parts of the value (`5 m/s x`), or a value SymPy can't parse. The underlying error is chained as `__cause__`. |
| `UnitConversionError` | The unit can't be converted to SI base units. |
| `QuantityParamsError` | A `QuantityParams` field is invalid. |

```python
from lambdafeedback.units import QuantityError

try:
    parse_quantity("2 m)", QuantityParams())
except QuantityError as error:
    print(error, error.expression)  # Unexpected END_DELIMITER ')' at position 3.  2 m)
```

## Known limitations

- Prefixes attach to any unit, including imperial ones (`kft` is a kilofoot).
  Where a prefixed symbol is also another unit's symbol, the unit wins: with
  `common` units, `min` is a minute; without them, it is a milli-inch.
- With the `common` set, `d` is a day, `a` is an are and `h` is an hour, even
  though they are also prefix symbols.
- `kΩ` is not recognised. Prefixed ohms must be written `kO` or `kiloohm`.
- `reverted_units` also reports the group enclosing a unit, with garbled
  positions (e.g. for `2 kg + 3`). The entry for the unit itself is correct.
- The unit's LaTeX preview removes whitespace, so in LaTeX input the value and
  unit must be separated with `~`.
- `QuantityParams` instances aren't hashable.

## Changelog

See [CHANGELOG.md](https://github.com/m-messer/lambda-feedback-packages/blob/main/units/CHANGELOG.md).

## License

MIT
