"""Grammar and parser for physical quantities such as ``9.81 m/s^2``."""

from __future__ import annotations

import re
from collections.abc import Callable
from functools import cache
from typing import Any, NamedTuple

from lambdafeedback.slr_parsing import (
    ExprNode,
    SLRParser,
    TokenProduction,
    TokenSpec,
    catch_undefined,
    create_node,
    group,
    infix,
    insert_infix,
    relabel,
    remove_tag,
)

from .data import SI_PREFIXES, units_in
from .errors import QuantityParseError
from .params import Strictness
from .tags import QuantityTag

_NUMBER_RE = re.compile(r"^-?(0|[1-9]\d*)?(\.\d+)?(?<=\d)(e-?(0|[1-9]\d*))?")


class UnitDictionaries(NamedTuple):
    """Spelling → canonical unit name, for recognising units in the input."""

    units: dict[str, str]
    """Unit names and symbols (and alternative spellings, in natural mode)."""
    prefixed_units: dict[str, str]
    """Prefixed forms, e.g. ``km`` / ``kilom`` / ``kilometre`` → ``kilometre``."""
    units_end: dict[str, str]
    """Forms only accepted as a whole word (plurals, in natural mode)."""
    prefixed_units_end: dict[str, str]


def unit_dictionaries(unit_sets: frozenset[str], strictness: Strictness) -> UnitDictionaries:
    selected = units_in(unit_sets)
    units = {unit.name: unit.name for unit in selected}
    short_to_long = {unit.symbol: unit.name for unit in selected}
    long_to_short = {unit.name: unit.symbol for unit in selected}
    units_end: dict[str, str] = {}
    if strictness == "natural":
        for unit in selected:
            units.update({alternative: unit.name for alternative in unit.alternatives})
            units_end.update({plural: unit.name for plural in unit.plurals})
            long_to_short.update({form: unit.symbol for form in (*unit.alternatives, *unit.plurals)})

    prefixed_units = dict(units)
    for form, name in units.items():
        for prefix in SI_PREFIXES:
            prefixed_units[prefix.name + form] = prefix.name + name
            # Skip prefixed short forms that are also the symbol of another unit
            short = long_to_short[form]
            if prefix.symbol + short not in short_to_long:
                prefixed_units[prefix.symbol + short] = prefix.name + name
            if prefix.name + short not in short_to_long:
                prefixed_units[prefix.name + short] = prefix.name + name
    # Symbols written as one non-ASCII letter ("Ω" for the ohm, whose ASCII symbol
    # is "O") are symbols in both modes, and take prefixes ("kΩ").
    symbol_alternatives = {
        alternative: unit.name
        for unit in selected
        for alternative in unit.alternatives
        if len(alternative) == 1 and alternative.isalpha() and not alternative.isascii()
    }
    for alternative, name in symbol_alternatives.items():
        prefixed_units.setdefault(alternative, name)
        for prefix in SI_PREFIXES:
            if prefix.symbol + alternative not in short_to_long:
                prefixed_units[prefix.symbol + alternative] = prefix.name + name
    prefixed_units_end = dict(units_end)
    for form, name in units_end.items():
        for prefix in SI_PREFIXES:
            prefixed_units_end[prefix.name + form] = prefix.name + name
    return UnitDictionaries(
        {**units, **symbol_alternatives, **short_to_long}, prefixed_units, units_end, prefixed_units_end
    )


def quantity_tag_handler(strictness: Strictness) -> Callable[[ExprNode], set[Any]]:
    """Tag handler deciding which subtrees are units, numbers or other (value) text."""

    def tag_handler(node: ExprNode) -> set[Any]:
        tags: set[Any] = set().union(*(child.tags for child in node.children))
        children = node.children
        if node.label == "UNIT":
            tags.add(QuantityTag.UNIT)
        elif node.label == "NUMBER":
            tags.add(QuantityTag.NUMBER)
        elif node.label == "NON-UNIT":
            tags.add(QuantityTag.NON_UNIT)
        elif (
            node.label == "POWER" and QuantityTag.UNIT in children[0].tags and children[1].tags == {QuantityTag.NUMBER}
        ):
            tags.remove(QuantityTag.NUMBER)  # a unit to a numeric power is a unit
        elif node.label == "SOLIDUS" and children[0].content == "1" and children[1].tags == {QuantityTag.UNIT}:
            tags.remove(QuantityTag.NUMBER)  # 1/unit is a unit
        elif node.label == "SOLIDUS" and children[0].tags == {QuantityTag.NUMBER} == children[1].tags:
            pass  # number/number stays a number
        elif node.label in ("PRODUCT", "SOLIDUS", "POWER"):
            if tags & {QuantityTag.NUMBER, QuantityTag.NON_UNIT, QuantityTag.REJECTED_UNIT}:
                tags.discard(QuantityTag.UNIT)
                if QuantityTag.NUMBER in tags:
                    tags.add(QuantityTag.NON_UNIT)
        elif node.label == "SPACE" and QuantityTag.NON_UNIT in children[1].tags:
            tags.discard(QuantityTag.UNIT)
        elif node.label == "GROUP" and not node.content[0] + node.content[1]:
            # Juxtaposition (a group without delimiters)
            if strictness == "strict":
                node.children = [remove_tag(child, QuantityTag.UNIT) for child in children]
                if QuantityTag.UNIT in tags:
                    tags.remove(QuantityTag.UNIT)
                    tags.add(QuantityTag.REJECTED_UNIT)
            elif any(QuantityTag.NON_UNIT in child.tags for child in children):
                tags.discard(QuantityTag.UNIT)
        return tags

    return tag_handler


def _raise(message: str) -> Callable[..., Any]:
    def action(*args: Any) -> Any:
        raise QuantityParseError(message)

    return action


def _juxtaposition_natural(production: TokenProduction, output: list[Any], tag_handler: Any) -> list[Any]:
    """Units written next to each other form a unit (``kg m``); anything else is a value group."""

    def is_unit(item: Any) -> bool:
        if not isinstance(item, ExprNode):
            return bool(item.label == "UNIT")
        if item.label == "GROUP":
            return bool(item.tags == {QuantityTag.UNIT})
        return QuantityTag.UNIT in item.tags

    pair = output[-2:]
    if all(is_unit(item) for item in pair):
        return insert_infix(" ", "SPACE")(production, output, tag_handler)
    for item in pair:
        if is_unit(item):
            item.tags.add(QuantityTag.NON_UNIT)
    return group(2, empty=True)(production, output, tag_handler)


@cache
def build_quantity_parser(unit_sets: frozenset[str], strictness: Strictness) -> SLRParser:
    """The quantity parser for these unit sets and strictness (built once per combination)."""
    dictionaries = unit_dictionaries(unit_sets, strictness)

    if strictness == "strict":
        units = {**dictionaries.units, **dictionaries.prefixed_units}
        longest = max(map(len, units), default=0)

        def starts_with_unit(string: str) -> tuple[str | None, str | None]:
            """The longest unit spelling the string starts with."""
            for k in range(longest, 0, -1):
                unit = units.get(string[:k])
                if unit is not None:
                    return string[:k], unit
            return None, None

    else:
        units = {**dictionaries.prefixed_units, **dictionaries.units}
        units_end = {**dictionaries.prefixed_units_end, **dictionaries.units_end}
        unit_chars = set("".join([*units, *units_end]))

        def starts_with_unit(string: str) -> tuple[str | None, str | None]:
            """Within the leading run of unit characters: a whole-word form, else the longest prefix that is a unit."""
            end = next((k for k, char in enumerate(string) if char not in unit_chars), len(string))
            word = string[:end]
            if not word:
                return None, None
            if word in units_end:
                return word, units_end[word]
            for k in range(len(word), -1, -1):
                unit = units.get(word[:k])
                if unit is not None:
                    return word[:k], unit
            return None, None

    def starts_with_number(string: str) -> tuple[str | None, str | None]:
        match = _NUMBER_RE.match(string)
        number = match.group() if match is not None else None
        return number, number

    token_list: list[TokenSpec] = [
        ("START", "START"),
        ("END", "END"),
        ("NULL", "NULL"),
        (" +", "SPACE"),
        (r" *\* *", "PRODUCT"),
        (" */ *", "SOLIDUS"),
        (r" *\^ *", "POWER"),
        (r" *\*\* *", "POWER"),
        (r"\( *", "START_DELIMITER"),
        (r" *\)", "END_DELIMITER"),
        ("N", "NUMBER", starts_with_number),
        ("U", "UNIT", starts_with_unit),
        ("V", "NON-UNIT", catch_undefined),
        ("Q", "QUANTITY_NODE", None),
    ]
    juxtaposition = group(2, empty=True) if strictness == "strict" else _juxtaposition_natural
    productions = [
        ("START", "Q", relabel),
        *(("Q", f"Q{operator}Q", infix) for operator in " */"),
        ("Q", "QQ", juxtaposition),
        ("Q", "Q^Q", infix),
        ("Q", "(Q)", group(1)),
        ("Q", "U", create_node),
        ("Q", "N", create_node),
        ("Q", "V", create_node),
    ]
    error_handler = [
        (
            lambda items, next_symbol: next_symbol.label == "NULL",
            _raise("Parser reached impossible state: NULL token."),
        ),
        (
            lambda items, next_symbol: next_symbol.label == "START",
            _raise("Parser reached impossible state: START token."),
        ),
        (lambda items, next_symbol: next_symbol.label == "END", _raise("Input ended before expression was completed.")),
        (
            lambda items, next_symbol: next_symbol.label in ("PRODUCT", "SOLIDUS", "POWER"),
            _raise("Infix operator requires an argument on either side."),
        ),
    ]
    return SLRParser(
        token_list,
        productions,
        "START",
        "END",
        "NULL",
        tag_handler=quantity_tag_handler(strictness),
        error_handler=error_handler,
    )
