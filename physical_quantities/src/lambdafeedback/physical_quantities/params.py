"""Typed parameters for physical quantities."""

from __future__ import annotations

import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, Self, get_args

from lambdafeedback.expression_parsing import ExpressionParams

from .data import UNIT_SETS
from .errors import QuantityParamsError

MAX_INPUT_LENGTH = 10_000
"""Longest input :func:`~lambdafeedback.physical_quantities.parse_quantity` reads, in characters.

A bound on its running time.
"""

Strictness = Literal["strict", "natural"]
"""``strict``: only unit names and symbols, units separated by ``*`` / ``/`` / spaces;
``natural`` also accepts alternative spellings and plurals, and units written together."""


@dataclass(frozen=True)
class QuantityParams(ExpressionParams):
    """:class:`ExpressionParams` plus how quantities (value and unit) are read."""

    strictness: Strictness = "natural"
    legacy_preprocessing: bool = False
    """Deprecated (removed in 1.0): rewrite the response the way the old ``legacy`` strictness did."""
    unit_sets: frozenset[str] = frozenset(UNIT_SETS)
    """Names from :data:`~lambdafeedback.physical_quantities.data.UNIT_SETS` whose units are recognised."""

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.strictness not in get_args(Strictness):
            raise QuantityParamsError("strictness", f"expected one of {get_args(Strictness)}, got {self.strictness!r}")
        if isinstance(self.unit_sets, str):
            raise QuantityParamsError("unit_sets", f"expected a set of names, got the string {self.unit_sets!r}")
        unit_sets = frozenset(self.unit_sets)
        if unknown := unit_sets - UNIT_SETS.keys():
            raise QuantityParamsError(
                "unit_sets", f"unknown unit sets {sorted(unknown)}, expected any of {list(UNIT_SETS)}"
            )
        object.__setattr__(self, "unit_sets", unit_sets)
        if self.legacy_preprocessing:
            warnings.warn(
                "legacy_preprocessing is deprecated and will be removed in 1.0; "
                "use strictness='natural' (the default) instead.",
                DeprecationWarning,
                stacklevel=3,
            )

    @classmethod
    def from_dict(cls, params: Mapping[str, Any]) -> Self:
        """Build from evaluation-function parameters.

        ``strictness: "legacy"`` (deprecated) means natural strictness with
        legacy preprocessing; ``units_string`` names the unit sets, separated
        by spaces or commas (e.g. ``"SI common imperial"``).

        Raises :class:`QuantityParamsError` for an unknown strictness or unit set.
        """
        values = dict(params)
        if values.get("strictness") == "legacy":
            values["strictness"] = "natural"
            values["legacy_preprocessing"] = True
        units_string = values.pop("units_string", None)
        if units_string is not None:
            if not isinstance(units_string, str):
                raise QuantityParamsError("units_string", f"expected a string, got {units_string!r}")
            values["unit_sets"] = frozenset(units_string.replace(",", " ").split())
        return super().from_dict(values)
