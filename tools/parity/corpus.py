"""Parity corpus: plain data, independent of any package API.

The probe outputs in ``baseline.json`` were captured from the v0.1 extraction
(compareExpressions' code) with these inputs. Quantity cases are frozen copies
of the response strings in the v0.1 units test suites; the rest are
hand-picked to cover each preprocessing feature.
"""

from typing import Any

CRITERIA_STRINGS = [
    *(
        s
        for comparison in ["=", ">", "<", ">=", "<="]
        for s in (
            f"a {comparison} b",
            f"response {comparison} b",
            f"a {comparison} response",
            f"response {comparison} answer",
        )
    ),
    "response = b*answer",
    "response = q where q = a*b",
    "response = q+p where q = a*b; p = b*c",
    "response written as answer",
    "response written as a*b*c",
    "response - answer = 0",
    "response proportional to answer",
    "response contains a",
]

EXPRESSION_VARIANTS: dict[str, dict[str, Any]] = {
    "default": {},
    "implicit_higher": {"convention": "implicit_higher_precedence", "elementary_functions": True},
    "elementary": {"elementary_functions": True},
    "strict": {"strict_syntax": True},
    "complex": {"complexNumbers": True, "elementary_functions": True},
    "symbols": {
        "elementary_functions": True,
        "plus_minus": "±",
        "minus_plus": "∓",
        "symbols": {
            "bc": {"latex": "b_c", "aliases": ["bc"]},
            "lambda": {"latex": r"\Lambda_0", "aliases": ["lam"]},
            "x_1": {"latex": "x_{1}", "aliases": ["x1", "xone"]},
            "mu": {"latex": r"\mu", "aliases": ["μ"]},
            "T_dot": {"latex": r"\dot{T}", "aliases": ["Tdot", ""]},
        },
    },
    "assumptions": {
        "elementary_functions": True,
        "symbol_assumptions": "('a','positive') ('n','integer') ('f','function') ('c','constant')",
    },
}

EXPRESSION_INPUTS = [
    # Basic arithmetic and implicit multiplication
    "x+1",
    "2x",
    "2 x y",
    "ab",
    "a/bc",
    "1/ab",
    "a/b/c",
    "a/bcd",
    "2(x+1)",
    "(x+1)(x-1)",
    "x^2",
    "x**2",
    "2x^2y",
    "-x",
    "--x",
    "3.14x",
    "10^-3",
    "1e-3",
    "2.5e3x",
    "sqrt(2)x",
    # Euler's number and E/e symbols
    "E",
    "e",
    "2E",
    "xE",
    "E*x",
    "e^x",
    "E^2",
    "exp(1)",
    # Brackets and absolute values
    "[x+1]",
    "{x+1}*{x-1}",
    "[x+1)",
    "|x|",
    "|x|+|y|",
    "2|x-1|",
    "|x|y|z|",
    "||x||",
    # Sets, plus/minus and equalities
    "{1, 2, 3}",
    "{x, -x}",
    "x plus_minus 1",
    "plus_minus x",
    "plus_minus",
    "1 ± x",
    "x ∓ 2",
    "x = 2",
    "y = 2x + 1",
    "a=b=c",
    # Greek letters and unicode
    "alpha + beta",
    "α + β",
    "2πr",
    "lambda x",
    "λ",
    "lam + lambda",
    "mu + μ",
    "x − 1",
    "x – 1",
    # Functions
    "sin(x)",
    "sin x",
    "arcsin(x)",
    "ln(x)",
    "log(x, 2)",
    "Abs(x)",
    "abs(x)",
    "cosh(x)^2 - sinh(x)^2",
    "Integral(x, x)",
    "diff(x^2, x)",
    # Complex numbers
    "I",
    "1 + 2I",
    "3e^(I*pi)",
    # Symbols with aliases / multi-character symbols
    "bc*d",
    "a/bcd",
    "x1 + xone",
    "x_1^2",
    "Tdot + T_dot",
    # Python keywords
    "as",
    "a s",
    # Assumptions
    "f(x)",
    "n + a + c",
    # Garbage
    "",
    "x***2",
    "(x",
    "x +",
]

QUANTITY_VARIANTS: dict[str, dict[str, Any]] = {
    "strict_si": {"units_string": "SI", "strictness": "strict", "elementary_functions": True},
    "strict_all": {"units_string": "SI common imperial", "strictness": "strict"},
    "natural_si": {"units_string": "SI", "strictness": "natural", "elementary_functions": True},
    "natural": {"units_string": "SI common imperial", "strictness": "natural", "elementary_functions": True},
    "legacy": {"units_string": "SI common imperial", "strictness": "legacy"},
}

_TEST_SUITE_CASES = [
    "q",
    "10",
    "-10.5*4",
    "pi*5",
    "5*pi",
    "sin(-10.5*4)",
    "kilogram/(metre second^2)",
    "metre^(3/2)",
    "10 kilogram/(metre second^2)",
    "10 kilogram*metre/second**2",
    "-10.5 kg m/s^2",
    "10 kilogram*metre*second**(-2)",
    "10*pi kilogram*metre/second^2",
    "(5.27*pi/sqrt(11) + 5*7)^(4.3)",
    "(kilogram megametre^2)/(fs^4 daA)",
    "(5.27*pi/sqrt(11) + 5*7)^(4.3) (kilogram megametre^2)/(fs^4 daA)",
    "(5.27*pi/sqrt(11) + 5*7)^(2+2.3) (kilogram megametre^2)/(fs^4 daA)",
    "(5*27/11 + 5*7)^(2*3) (kilogram megametre^2)/(fs^4 daA)",
    "(pi+10) kg*m/s^2",
    "10 kilogram*metre/second^2",
    "10 kg*m/s^2",
    " 10 kg m/s^2 ",
    "10 gram/metresecond",
    "10 g/sm",
    "10 s/g + 5 gram*second^2 + 7 ms + 5 gram/second^3",
    "10 kg m/s^2 + 10 kg m/s^2",
    "10 second/gram * 7 ms * 5 gram/second",
    "pi+metre second+pi",
    "1/s^2",
    "5/s^2",
    "10 1/s^2",
    "fs^4daA",
    "mmPas",
    "kilogrammetersecondAmperes",
    "kilogram/(metresecond^2)",
    "10 kilogram/(metresecond^2)",
    "10 kilogrammetre/second**2",
    "10 kilogrammetre/second^2",
    "10 kgm/s^2",
    "-10.5 kgm/s^2",
    "10 kilogrammetresecond**(-2)",
    "10*pi kilogrammetre/second^2",
    "(kilogrammegametre^2)/(fs^4daA)",
    "(5.27*pi/sqrt(11) + 5*7)^(4.3) (kilogrammegametre^2)/(fs^4daA)",
    "mmg",
    "(pi+10) kgm/s^2",
    "10 s/g + 5 gramsecond^2 + 7 ms + 5 gram/second^3",
    "10 kgm/s^2 + 10 kgm/s^2",
]

# fmt: off
_UNIT_NAMES_AND_SYMBOLS = [
    '"', "'", "A", "B", "Bq", "C", "Ci", "F", "Gy", "H", "Hz", "J", "K", "L", "N", "Np", "O", "Pa", "R", "S", "Sv",
    "T", "V", "W", "Wb", "a", "ampere", "angleminute", "anglesecond", "angstrom", "are", "astronomical_unit",
    "atomic_mass_unit", "au", "b", "bar", "barn", "becquerel", "bel", "candela", "cd", "coulomb", "curie", "d", "day",
    "deg", "degree", "eV", "electronvolt", "farad", "fl_oz", "fluid_ounce", "foot", "ft", "g", "gal", "gallon", "gi",
    "gill", "gram", "gray", "h", "ha", "hectare", "henry", "hertz", "hour", "in", "inch", "joule", "kat", "katal",
    "kelvin", "kn", "knot", "lb", "litre", "lm", "lumen", "lux", "lx", "m", "metre", "metricton", "mi", "mile", "min",
    "minute", "mol", "mole", "nautical_mile", "neper", "newton", "nmi", "ohm", "ounce", "oz", "pascal", "pint",
    "pound", "pt", "qt", "quart", "r", "rad", "radian", "rem", "roentgen", "s", "second", "siemens", "sievert", "sr",
    "st", "steradian", "stone", "t", "tesla", "u", "volt", "watt", "weber", "yard", "yd", "Å",
]
# fmt: on

_EXTRA_QUANTITY_CASES = [
    # Plurals and alternative spellings
    "2 litres",
    "2 liters",
    "2 metres",
    "2 meters",
    "3 newtons",
    "3 Newton",
    "1 Ω",
    "5 °",
    # Prefixes
    "5 km",
    "5 kilometre",
    "5 kilo metre",
    "5 k m",
    "3 µs",
    "3 μs",
    "3 micro second",
    "2 dekametre",
    "7 mPa",
    # Legacy-style spacing and multiplication
    "newton*metre",
    "100Pa",
    "100 m Pa",
    "100 m* Pa",
    "100* Pa",
    # Groups and juxtaposition
    "(2 m) s",
    "2 (m s)",
    "(2 kg) (m/s)",
    "x m",
    "2 x kg",
    "5 m/s x",
    # Errors
    "",
    "10 kg *",
    "* m",
]

QUANTITY_INPUTS = _TEST_SUITE_CASES + [f"10 {u}" for u in _UNIT_NAMES_AND_SYMBOLS] + _EXTRA_QUANTITY_CASES
