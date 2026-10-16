# lambdafeedback-units

Parse physical quantities such as `9.81 m/s^2` or `5 kilometres/hour` into a
value and a unit, convert them to SI base units, and compare dimensions. Built
on [SymPy](https://www.sympy.org/) for
[Lambda Feedback](https://github.com/lambda-feedback) evaluation functions,
where the input is a learner's typed answer: the parser accepts natural
spellings (`metres`, `kg m/s`, and `μs` after preprocessing) and tells you
which part is the value and which is the unit.

Originally extracted from the
[compareExpressions](https://github.com/lambda-feedback/compareExpressions)
evaluation function.

## Install

From git (not on PyPI yet):

```bash
pip install "lambdafeedback-units @ git+https://github.com/lambda-feedback/lambda-feedback-packages.git@v0.3.0-rc.3#subdirectory=units"
```

Install the packages it depends on (`slr_parsing`, `expression_parsing`) from the same tag; see the [repository README](../README.md#install).

Requires Python 3.12 or later. The import root is `lambdafeedback.units`.

## Quick start

```python
from lambdafeedback.units import QuantityParams, parse_quantity, same_dimension

q = parse_quantity("5 km/h", QuantityParams())
q  # PhysicalQuantity(value='5', unit='kilometre/hour')
q.value.content_string()  # '5'
q.unit.content_string()  # 'kilometre/hour'   (symbols become unit names)
q.standard_values  # (5*5/18,)        (SymPy, unevaluated; .simplify() → 25/18)
q.standard_unit  # metre/second
q.unit_factor  # 5/18
q.latex  # 5~\frac{\mathrm{kilometre}}{\mathrm{hour}}

q.base_dimension  # length/time

same_dimension(q, parse_quantity("3 m/s", QuantityParams()))  # True
same_dimension(q, parse_quantity("3 m", QuantityParams()))  # False
```

Either part may be missing: `parse_quantity("kg", ...)` has `value is None`, and
`parse_quantity("2x", ...)` has `unit is None`. `·`, `⋅` and `×` are read as `*`,
and any whitespace (tabs, newlines, no-break or thin spaces) as a space.

For learners' input, run `preprocess_quantity` first. It rewrites alternative
prefix spellings such as `μ`, `µ` and `deka`, and collapses whitespace.
Without it, `2 µm` is read as a value with no unit.

```python
from lambdafeedback.units import preprocess_quantity

params = QuantityParams()
text = preprocess_quantity("2 µm", params, name="response")  # '2 microm'
parse_quantity(text, params)  # PhysicalQuantity(value='2', unit='micrometre')
```

### What a `PhysicalQuantity` holds

| Attribute | Meaning |
|---|---|
| `value`, `unit` | The value and unit parse trees (`ExprNode`), or `None`. `content_string()` gives the normalised text. |
| `standard_values` | The value with the unit's factor applied, as a tuple of SymPy expressions (several for a value such as `{1, 2}` or `±`), so it is the quantity's magnitude in SI base units. |
| `standard_unit` | The unit in SI base units, without its numeric factor. |
| `expanded_unit` | The unit in SI base units, with its factor. |
| `unit_factor` | The factor between the unit and SI base units. |
| `base_dimension` | The unit's dimension in terms of `length`, `mass`, `time`, `electric_current`, `temperature`, `amount_of_substance` and `luminous_intensity` (`km/h` gives `length/time`). `1` for a quantity without a unit, and for angles. Compare two quantities with `same_dimension(a, b)`. |
| `dimension` | The same, but keeping the unit's factor: `km/h` gives `10**3*length/((3600*time))`. |
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
| `strictness` | `"natural"` | `"strict"`: only unit names and symbols, separated by `*`, `/` or spaces. `"natural"` also accepts alternative spellings (`meter`, `Ohm`) and plurals (`metres`), and units written together (`kgm`). |
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
(`rad` is the radiation-dose unit). The ohm is `Ω` or, in plain ASCII, `O`, in
both modes and with prefixes (`kΩ`, `kO`).

## Errors

All errors derive from `QuantityError`, which is a `ValueError`, and carry
`expression` (the input) and `name` (e.g. `"response"`):

| Exception | Raised when |
|---|---|
| `QuantityParseError` | The input can't be read as a quantity: unbalanced brackets, a dangling operator, a unit between parts of the value (`5 m/s x`), a number inside the unit (`2 m 3 s`, `1 hour 30 minutes`), a temperature in °C or °F, a number with more than 1000 digits or an exponent beyond ±1000, a unit's exponent that isn't a number or is beyond ±`MAX_UNIT_EXPONENT` (100), input longer than `MAX_INPUT_LENGTH` (10,000 characters) or too deeply nested to process, or a value SymPy can't parse. The underlying error is chained as `__cause__`. |
| `DisallowedUnitError` | A `QuantityParseError`: the input spells out a unit from a unit set that isn't selected, by name, alternative spelling or plural, with or without a prefix (`10 litre`, `3 feet`, `5 °` with only `SI`). `unit` is the unit's name and `unit_sets` the sets that contain it. Symbols (`L`, `h`) aren't checked, since they are more likely variables. |
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
- `reverted_units` also reports the group enclosing a unit, with garbled
  positions (e.g. for `2 kg + 3`). The entry for the unit itself is correct.
- Function names that contain unit symbols are reported in `reverted_units`
  (`sin` gives `s` and `in`), although the value is parsed, and previewed, as
  the function call.
- LaTeX input (`is_latex=True`) is only partly supported. LaTeX spacing (`~`,
  `\,`) and `\mathrm{...}`/`\text{...}` are understood, so `2~\mathrm{m}`
  works, but the unit must otherwise be written in plain syntax: `m/s^2`, not
  `\frac{m}{s^{2}}` or `s^{-1}`.
- In natural mode, a function call is split into units: `2 sqrt(m)` reads
  `sqrt` as second·quecto-radian·tonne. Capitalisation matters too: `2 Kg` is
  kelvin·gram, not kilogram.
- Bracketed groups are kept whole, so `(2 m) s` reads the whole input as a unit,
  with the `2` as a factor.
- Temperatures are in kelvin only. Celsius and Fahrenheit raise an error,
  because their conversions aren't proportional.
- A unit *symbol* from a set that isn't selected is read as letters in the
  value: with only `SI`, `5 h` is the value `5*h` with no unit (spelled-out
  names such as `hour` raise `DisallowedUnitError`). Check
  `quantity.unit is None` when a unit is required.
- `QuantityParams` instances aren't hashable.
- Legacy preprocessing (`strictness: "legacy"`, deprecated) is skipped for input
  longer than `MAX_LEGACY_LENGTH` (1,000 characters): its rewrites take time
  cubic in the length on some input.

## Changelog

See [CHANGELOG.md](https://github.com/lambda-feedback/lambda-feedback-packages/blob/main/units/CHANGELOG.md).

## License

MIT
