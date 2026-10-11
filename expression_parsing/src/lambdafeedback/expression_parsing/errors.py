"""Exceptions raised by the expression_parsing package."""

from __future__ import annotations


class ExpressionParsingError(ValueError):
    """An expression or its parsing parameters could not be parsed."""

    def __init__(self, text: str, *, expression: str | None = None) -> None:
        super().__init__(text)
        self.expression = expression


class UnknownConventionError(ExpressionParsingError):
    """``convention`` is not one of the recognised implicit-multiplication conventions."""

    def __init__(self, convention: str) -> None:
        super().__init__(f"Unknown convention {convention!r}.")
        self.convention = convention


class InvalidParameterError(ExpressionParsingError):
    """A parameter has the wrong type (e.g. ``"false"`` for a boolean); ``name`` is its field name."""

    def __init__(self, name: str, message: str) -> None:
        super().__init__(f"Invalid parameter {name!r}: {message}")
        self.name = name


class SymbolAssumptionError(ExpressionParsingError):
    """A ``symbol_assumptions`` parameter is malformed or names an invalid assumption.

    ``text`` is the raw offending substring (when the parameter as a whole was
    malformed); ``symbol``/``assumption`` identify a specific bad pair.
    """

    def __init__(
        self, message: str, *, text: str | None = None, symbol: str | None = None, assumption: str | None = None
    ) -> None:
        super().__init__(message)
        self.text = text
        self.symbol = symbol
        self.assumption = assumption


class LatexParseError(ExpressionParsingError):
    """A LaTeX expression could not be parsed.

    ``expression`` is the LaTeX that failed. ``symbol`` is set instead when
    it was a task symbol's LaTeX rather than the response.
    """

    def __init__(self, text: str, *, expression: str | None = None, symbol: str | None = None) -> None:
        super().__init__(text, expression=expression)
        self.symbol = symbol


class BracketNotationError(ExpressionParsingError):
    """Brackets closed with a different kind than opened (e.g. ``[x+y)``).

    ``original`` is the expression as written. ``expression`` is a
    best-effort rewrite (every bracket kind collapsed to ``()``): often this
    parses fine (a wrong-*kind* mismatch), but it may still fail if the
    brackets are genuinely unbalanced.
    """

    expression: str

    def __init__(self, expression: str, *, original: str) -> None:
        super().__init__(f"Mismatched brackets in {original!r}.", expression=expression)
        self.original = original


class AbsoluteValueNotationError(ExpressionParsingError):
    """``|...|`` pairs that could not be matched unambiguously.

    ``expression`` is a best-guess rewrite of ``|...|`` as ``Abs(...)``;
    ``name`` (e.g. ``"response"``), if given, identifies what was being converted.
    """

    expression: str

    def __init__(self, expression: str, *, name: str | None = None) -> None:
        where = f" in {name}" if name is not None else ""
        super().__init__(f"Ambiguous absolute value notation{where}: {expression!r}.", expression=expression)
        self.name = name
