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
    """A LaTeX expression (or a symbol's LaTeX) could not be parsed."""

    def __init__(
        self,
        text: str,
        *,
        symbol: str | None = None,
        expression: str | None = None,
        response: str | None = None,
        wrapper: str | None = None,
    ) -> None:
        super().__init__(text)
        self.symbol = symbol
        self.expression = expression
        self.response = response
        self.wrapper = wrapper


class BracketNotationError(ExpressionParsingError):
    """Brackets closed with a different kind than opened (e.g. ``[x+y)``).

    ``original`` is the expression as written. ``expression`` is a
    best-effort rewrite (every bracket kind collapsed to ``()``): often this
    parses fine (a wrong-*kind* mismatch), but it may still fail if the
    brackets are genuinely unbalanced.
    """

    def __init__(self, expression: str, *, original: str) -> None:
        super().__init__(f"Mismatched brackets in {original!r}.")
        self.expression: str = expression
        self.original = original


class AbsoluteValueNotationError(ExpressionParsingError):
    """``|...|`` pairs that could not be matched unambiguously.

    ``expression`` is a best-guess rewrite of ``|...|`` as ``Abs(...)``;
    ``name`` (e.g. ``"response"``) identifies what was being converted.
    """

    def __init__(self, expression: str, name: str) -> None:
        super().__init__(f"Ambiguous absolute value notation in {name}: {expression!r}.")
        self.expression: str = expression
        self.name = name
