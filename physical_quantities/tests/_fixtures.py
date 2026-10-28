"""Test fixtures for the physical quantities package.

``default_parameters`` mirrors the quantity-specific defaults of the
physical-quantity context in compareExpressions (app/context/physical_quantity.py);
the symbolic defaults are those of ``ExpressionParams``. Vendored here so the
ported quantity tests do not depend on the app's core evaluation layer.
"""

default_parameters = {
    "physical_quantity": True,
    "strictness": "natural",
    "units_string": "SI common imperial",
}
