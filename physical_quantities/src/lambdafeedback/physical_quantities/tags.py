"""Tags on quantity parse-tree nodes, used to tell a quantity's value from its unit."""

from __future__ import annotations

from enum import Enum


class QuantityTag(Enum):
    UNIT = 1
    """The subtree is (part of) a unit."""
    NON_UNIT = 2
    """The subtree contains text that is not a unit or a number (a value expression)."""
    NUMBER = 3
    """The subtree contains a number."""
    REJECTED_UNIT = 4
    """Units written next to each other in strict mode, which strict syntax doesn't accept as a unit."""
