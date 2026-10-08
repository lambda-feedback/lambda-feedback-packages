"""Units and prefixes, and their conversion to SI base units.

Remarks: kelvin is the only temperature scale; angle measures, the bel and
the neper are all treated as dimensionless, with the radian and the
steradian equal to 1 (so ``degree`` is ``pi/180``). The gram (not the
kilogram) is the base unit of mass, so that SI prefixes apply uniformly.

Every unit set's symbols are recognised, and any SI prefix can be attached to
any unit (``kft`` is a kilofoot). Where a prefixed form is also the symbol of
another unit, the unit wins: with the ``common`` set, ``min`` is a minute, not
a milli-inch. Some symbols differ from the SI ones to avoid collisions:
``r`` is the radian (``rad`` is the absorbed-dose unit) and ``O`` is the ohm.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import NamedTuple


class Prefix(NamedTuple):
    name: str
    symbol: str
    factor: str
    """Multiplier as a SymPy expression string, e.g. ``"(10**3)"``."""
    alternatives: tuple[str, ...] = ()


class BaseUnit(NamedTuple):
    name: str
    symbol: str
    dimension: str
    alternatives: tuple[str, ...] = ()
    """Other spellings (e.g. ``meter``)."""
    plurals: tuple[str, ...] = ()
    """Plural forms, only accepted at the end of a unit (natural strictness)."""


class Unit(NamedTuple):
    name: str
    symbol: str
    si_expansion: str
    """The unit in SI units, as a SymPy expression string, e.g. ``"(metre*kilogram*second**(-2))"``."""
    alternatives: tuple[str, ...] = ()
    plurals: tuple[str, ...] = ()


# Table 5 of https://physics.nist.gov/cuu/Units/prefixes.html and https://www.bipm.org/en/cgpm-2022/resolution-3
SI_PREFIXES: tuple[Prefix, ...] = (
    Prefix("quetta", "Q", "(10**30)"),
    Prefix("ronna", "R", "(10**27)"),
    Prefix("yotta", "Y", "(10**24)"),
    Prefix("zetta", "Z", "(10**21)"),
    Prefix("exa", "E", "(10**18)"),
    Prefix("peta", "P", "(10**15)"),
    Prefix("tera", "T", "(10**12)"),
    Prefix("giga", "G", "(10**9)"),
    Prefix("mega", "M", "(10**6)"),
    Prefix("kilo", "k", "(10**3)"),
    Prefix("hecto", "h", "(10**2)"),
    Prefix("deca", "da", "(10**1)", ("deka",)),
    Prefix("deci", "d", "(10**(-1))"),
    Prefix("centi", "c", "(10**(-2))"),
    Prefix("milli", "m", "(10**(-3))"),
    Prefix("micro", "mu", "(10**(-6))", ("μ", "µ", "𝛍", "𝜇", "𝝁", "𝝻", "𝞵")),
    Prefix("nano", "n", "(10**(-9))"),
    Prefix("pico", "p", "(10**(-12))"),
    Prefix("femto", "f", "(10**(-15))"),
    Prefix("atto", "a", "(10**(-18))"),
    Prefix("zepto", "z", "(10**(-21))"),
    Prefix("yocto", "y", "(10**(-24))"),
    Prefix("ronto", "r", "(10**(-27))"),
    Prefix("quecto", "q", "(10**(-30))"),
)

# Table 1 of https://physics.nist.gov/cuu/Units/units.html (with gram instead of kilogram)
SI_BASE_UNITS: tuple[BaseUnit, ...] = (
    BaseUnit("metre", "m", "length", ("meter",), ("metres", "meters")),
    BaseUnit("gram", "g", "mass", (), ("grams",)),
    BaseUnit("second", "s", "time", (), ("seconds",)),
    BaseUnit("ampere", "A", "electric_current", ("Ampere",), ("amperes", "Amperes")),
    BaseUnit("kelvin", "K", "temperature", ("Kelvin",), ("kelvins", "Kelvins")),
    BaseUnit("mole", "mol", "amount_of_substance", (), ("moles",)),
    BaseUnit("candela", "cd", "luminous_intensity", ("Candela",), ("candelas", "Candelas")),
)

# Table 3 of https://physics.nist.gov/cuu/Units/units.html. Radian and steradian are in
# VERY_COMMON_UNITS (fewer collisions when substituting); degree Celsius is omitted.
SI_DERIVED_UNITS: tuple[Unit, ...] = (
    Unit("hertz", "Hz", "(second**(-1))", ("Hertz",)),
    Unit("newton", "N", "(metre*kilogram*second**(-2))", ("Newton",), ("newtons", "Newtons")),
    Unit("pascal", "Pa", "(metre**(-1)*kilogram*second**(-2))", ("Pascal",), ("pascals", "Pascals")),
    Unit("joule", "J", "(metre**2*kilogram*second**(-2))", ("Joule",), ("joules", "Joules")),
    Unit("watt", "W", "(metre**2*kilogram*second**(-3))", ("Watt",), ("watts", "Watts")),
    Unit("coulomb", "C", "(second*ampere)", ("Coulomb",), ("coulombs", "Coulombs")),
    Unit("volt", "V", "(metre**2*kilogram*second**(-3)*ampere**(-1))", ("Volt",), ("volts", "Volts")),
    Unit("farad", "F", "(metre**(-2)*(kilogram)**(-1)*second**4*ampere**2)", ("Farad",), ("farads", "Farads")),
    Unit(
        "ohm",
        "O",
        "(metre**2*kilogram*second**(-3)*ampere**(-2))",
        ("Ohm", "Ω", "𝛀", "𝛺", "𝜴", "𝝮", "𝞨"),
        ("ohms", "Ohms"),
    ),
    Unit("siemens", "S", "(metre**(-2)*kilogram**(-1)*second**3*ampere**2)", ("Siemens",)),
    Unit("weber", "Wb", "(metre**2*kilogram*second**(-2)*ampere**(-1))", ("Weber",), ("webers", "Webers")),
    Unit("tesla", "T", "(kilogram*second**(-2)*ampere**(-1))", ("Tesla",), ("teslas", "Teslas")),
    Unit("henry", "H", "(metre**2*kilogram*second**(-2)*ampere**(-2))", ("Henry",), ("henrys", "Henrys")),
    Unit("lumen", "lm", "(candela)", (), ("lumens",)),
    Unit("lux", "lx", "(metre**(-2)*candela)"),
    Unit("becquerel", "Bq", "(second**(-1))", ("Becquerel",), ("becquerels", "Becquerels")),
    Unit("gray", "Gy", "(metre**2*second**(-2))", ("Gray",), ("grays", "Grays")),
    Unit("sievert", "Sv", "(metre**2*second**(-2))", ("Sievert",), ("sieverts", "Sieverts")),
    Unit("katal", "kat", "(second**(-1)*mole)", ("Katal",), ("katals", "Katals")),
)

# Tables 6 and 7 of https://physics.nist.gov/cuu/Units/outside.html: the subset whose
# symbols are accepted.
VERY_COMMON_UNITS: tuple[Unit, ...] = (
    Unit("radian", "r", "(1)", (), ("radians",)),  # 'r', not 'rad', to avoid a collision with the rad
    Unit("steradian", "sr", "(1)", (), ("steradians",)),
    Unit("minute", "min", "(60*second)", (), ("minutes",)),
    Unit("hour", "h", "(3600*second)", (), ("hours",)),
    Unit("degree", "deg", "(pi/180)", ("°",), ("degrees",)),
    Unit("litre", "L", "(10**(-3)*metre**3)", ("liter",), ("litres", "liters")),
    Unit("metricton", "t", "(10**3*kilogram)", ("tonne",), ("tonnes",)),
    Unit("neper", "Np", "(1)", ("Neper",), ("nepers", "Nepers")),
    Unit("bel", "B", "((1/2)*2.30258509299405)", ("Bel",), ("bels", "Bels")),  # log(10) = 2.30258509299405
    Unit("electronvolt", "eV", "(1.60218*10**(-19)*joule)", (), ("electronvolts",)),
    Unit("atomic_mass_unit", "u", "(1.66054*10**(-27)*kilogram)", (), ("atomic_mass_units",)),
    Unit("angstrom", "Å", "(10**(-10)*metre)", ("Angstrom", "Ångström"), ("angstroms", "Angstroms")),
)

# Tables 6 and 7 of https://physics.nist.gov/cuu/Units/outside.html, and older units.
# Their symbols are recognised too, so including this set adds ambiguities ('d' is a
# day, 'a' an are).
COMMON_UNITS: tuple[Unit, ...] = (
    Unit("day", "d", "(86400*second)", (), ("days",)),
    Unit("angleminute", "'", "(pi/10800)"),
    Unit("anglesecond", '"', "(pi/648000)"),
    Unit("astronomical_unit", "au", "(149597870700*metre)", (), ("astronomical_units",)),
    Unit("nautical_mile", "nmi", "(1852*metre)", (), ("nautical_miles", "nauticalmiles")),  # symbol from Wikipedia
    Unit("knot", "kn", "((1852/3600)*metre/second)", (), ("knots",)),  # symbol from Wikipedia
    Unit("are", "a", "(10**2*metre**2)", (), ("ares",)),
    Unit("hectare", "ha", "(10**4*metre**2)", (), ("hectares",)),
    Unit("bar", "bar", "(10**5*pascal)", (), ("bars",)),
    Unit("barn", "b", "(10**(-28)*metre**2)", (), ("barns",)),
    Unit("curie", "Ci", "(3.7*10**10*becquerel)", ("Curie",), ("curies",)),
    Unit(
        "roentgen", "R", "(2.58*10**(-4)*second*ampere/(kilogram))", ("Roentgen", "Röntgen"), ("roentgens", "Roentgens")
    ),
    Unit("rad", "rad", "(10**(-2)*gray)", (), ("rads",)),
    Unit("rem", "rem", "(10**(-2)*sievert)", (), ("rems",)),
)

# UK imperial units, from https://en.wikipedia.org/wiki/Imperial_units, in SI units
IMPERIAL_UNITS: tuple[Unit, ...] = (
    Unit("inch", "in", "(0.0254*metre)", (), ("inches",)),
    Unit("foot", "ft", "(0.3048*metre)", (), ("feet",)),
    Unit("yard", "yd", "(0.9144*metre)", (), ("yards",)),
    Unit("mile", "mi", "(1609.344*metre)", (), ("miles",)),
    Unit("fluid_ounce", "fl_oz", "(0.00002841310625*metre**3)", (), ("fluid_ounces",)),
    Unit("gill", "gi", "(0.0001420653125*metre**3)", (), ("gills",)),
    Unit("pint", "pt", "(0.00056826125*metre**3)", (), ("pints",)),
    Unit("quart", "qt", "(0.0011365225*metre**3)", (), ("quarts",)),
    Unit("gallon", "gal", "(0.00454609*metre**3)", (), ("gallons",)),
    Unit("ounce", "oz", "(28.349523125*gram)", (), ("ounces",)),
    Unit("pound", "lb", "(0.45359237*kilogram)", (), ("pounds",)),
    Unit("stone", "st", "(6.35029318*kilogram)"),
)

AnyUnit = BaseUnit | Unit

UNIT_SETS: Mapping[str, tuple[AnyUnit, ...]] = MappingProxyType(
    {
        "SI": (*SI_BASE_UNITS, *SI_DERIVED_UNITS),
        "common": (*SI_BASE_UNITS, *SI_DERIVED_UNITS, *COMMON_UNITS, *VERY_COMMON_UNITS),
        "imperial": IMPERIAL_UNITS,
    }
)
"""Named unit sets (read-only); a quantity's ``unit_sets`` choose which units are recognised."""

ALL_UNITS: tuple[AnyUnit, ...] = (*SI_BASE_UNITS, *SI_DERIVED_UNITS, *COMMON_UNITS, *VERY_COMMON_UNITS, *IMPERIAL_UNITS)


def units_in(unit_sets: frozenset[str] | set[str]) -> tuple[AnyUnit, ...]:
    """The units of the given sets, each once, in table order."""
    return tuple(dict.fromkeys(unit for name, units in UNIT_SETS.items() if name in unit_sets for unit in units))


def _conversion_to_base_si() -> dict[str, str]:
    unprefixed = {unit.name: unit.si_expansion for unit in ALL_UNITS if isinstance(unit, Unit)}
    unprefixed.update({unit.name: unit.name for unit in SI_BASE_UNITS})
    prefixed = {
        prefix.name + name: f"({prefix.factor}*{expansion})"
        for prefix in SI_PREFIXES
        for name, expansion in unprefixed.items()
    }
    return {**unprefixed, **prefixed}


CONVERSION_TO_BASE_SI: Mapping[str, str] = MappingProxyType(_conversion_to_base_si())
"""Every unit name (with and without SI prefix) mapped to an expression in SI base units (read-only)."""
