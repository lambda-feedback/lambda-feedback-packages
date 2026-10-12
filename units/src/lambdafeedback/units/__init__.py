"""Physical quantities: unit data, parsing into value and unit, dimensional analysis.

Typical use::

    params = QuantityParams.from_dict(evaluation_params)
    quantity = parse_quantity("9.81 m/s^2", params)
    quantity.value, quantity.unit, quantity.base_dimension, quantity.standard_value
    same_dimension(quantity, parse_quantity("1 N/kg", params))  # True

Extracted from compareExpressions; unit-like text read as part of a value is
reported as :class:`RevertedUnit` facts in ``quantity.reverted_units``.
Previewing a response (LaTeX/SymPy rendering) is an app-layer concern and
lives in compareExpressions, not here.
"""

from importlib.metadata import PackageNotFoundError, version

from .data import (
    ALL_UNITS,
    COMMON_UNITS,
    CONVERSION_TO_BASE_SI,
    IMPERIAL_UNITS,
    SI_BASE_UNITS,
    SI_DERIVED_UNITS,
    SI_PREFIXES,
    UNIT_SETS,
    VERY_COMMON_UNITS,
    AnyUnit,
    BaseUnit,
    Prefix,
    Unit,
    units_in,
)
from .errors import DisallowedUnitError, QuantityError, QuantityParamsError, QuantityParseError, UnitConversionError
from .params import MAX_INPUT_LENGTH, QuantityParams, Strictness
from .parser import build_quantity_parser
from .preprocessing import MAX_LEGACY_LENGTH, preprocess_legacy, preprocess_quantity, transform_prefixes_to_standard
from .quantity import (
    MAX_UNIT_EXPONENT,
    PhysicalQuantity,
    RevertedUnit,
    parse_quantity,
    same_dimension,
)
from .tags import QuantityTag

try:
    __version__ = version("lambdafeedback-units")
except PackageNotFoundError:  # running from a source checkout that isn't installed
    __version__ = "0+unknown"

__all__ = [
    "ALL_UNITS",
    "COMMON_UNITS",
    "CONVERSION_TO_BASE_SI",
    "IMPERIAL_UNITS",
    "MAX_INPUT_LENGTH",
    "MAX_LEGACY_LENGTH",
    "MAX_UNIT_EXPONENT",
    "SI_BASE_UNITS",
    "SI_DERIVED_UNITS",
    "SI_PREFIXES",
    "UNIT_SETS",
    "VERY_COMMON_UNITS",
    "AnyUnit",
    "BaseUnit",
    "DisallowedUnitError",
    "PhysicalQuantity",
    "Prefix",
    "QuantityError",
    "QuantityParams",
    "QuantityParamsError",
    "QuantityParseError",
    "QuantityTag",
    "RevertedUnit",
    "Strictness",
    "Unit",
    "UnitConversionError",
    "__version__",
    "build_quantity_parser",
    "parse_quantity",
    "preprocess_legacy",
    "preprocess_quantity",
    "same_dimension",
    "transform_prefixes_to_standard",
    "units_in",
]
