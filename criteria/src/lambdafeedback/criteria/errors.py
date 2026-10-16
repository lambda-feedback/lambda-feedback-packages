"""Exceptions raised by the criteria package."""


class CriteriaError(Exception):
    """Base class for errors raised by the criteria package."""


class CriteriaGraphError(CriteriaError, ValueError):
    """A criteria graph was built or queried inconsistently."""


class CriteriaSyntaxError(CriteriaError, ValueError):
    """A criteria string is not well formed."""


class CriteriaEvaluationError(CriteriaError):
    """An evaluation node's ``evaluate`` function failed; the cause is chained."""

    def __init__(self, label: str) -> None:
        super().__init__(f"Evaluation node {label} failed.")
        self.label = label
