import os

import pytest

from lambdafeedback.units import (
    COMMON_UNITS,
    IMPERIAL_UNITS,
    SI_BASE_UNITS,
    SI_DERIVED_UNITS,
    VERY_COMMON_UNITS,
    QuantityParams,
    parse_quantity,
)

from ._fixtures import default_parameters

slr_strict_si_syntax_test_cases = [
    (
        "q",  # String that will be used as response / answer
        "q",  # Expected value
        None,  # Expected unit
        "q",  # Content of physical quantity after parsing
        "q",  # Expected LaTeX for value
        None,  # Expected LaTeX for unit
        ["response = answer_QUANTITY_MATCH"],
    ),  # criteria
    ("10", "10", None, "10", "10", None, ["NO_UNIT"]),
    (
        "-10.5*4",
        "-10.5*4",
        None,
        "-10.5*4",
        r"\left(-10.5\right) \cdot 4",  # Ideally parenthesis around -10.5 should be removed here
        None,
        ["NO_UNIT"],
    ),
    ("pi*5", "pi*5", None, "pi*5", r"\pi \cdot 5", None, ["NO_UNIT"]),
    ("5*pi", "5*pi", None, "5*pi", r"5 \cdot \pi", None, ["NO_UNIT"]),
    (
        "sin(-10.5*4)",
        "sin(-10.5*4)",
        None,
        "sin(-10.5*4)",
        r"\sin{\left(\left(-10.5\right) \cdot 4 \right)}",  # Ideally parenthesis around -10.5 should be removed here
        None,
        ["NO_UNIT"],
    ),
    (
        "kilogram/(metre second^2)",
        None,
        "kilogram/(metre second^2)",
        "kilogram/(metre second^2)",
        None,
        r"\frac{\mathrm{kilogram}}{\mathrm{metre}~\mathrm{second}^{2}}",
        ["NO_VALUE"],
    ),
    ("metre^(3/2)", None, "metre^(3/2)", "metre^(3/2)", None, r"\mathrm{metre}^{\frac{3}{2}}", ["NO_VALUE"]),
    (
        "10 kilogram/(metre second^2)",
        "10",
        "kilogram/(metre second^2)",
        "10 kilogram/(metre second^2)",
        "10",
        r"\frac{\mathrm{kilogram}}{\mathrm{metre}~\mathrm{second}^{2}}",
        ["FULL_QUANTITY", "NUMBER_VALUE"],
    ),
    (
        "10 kilogram*metre/second**2",
        "10",
        "kilogram*metre/second**2",
        "10 kilogram*metre/second**2",
        "10",
        r"\mathrm{kilogram}\cdot\frac{\mathrm{metre}}{\mathrm{second}^{2}}",
        ["FULL_QUANTITY", "NUMBER_VALUE"],
    ),
    (
        "-10.5 kg m/s^2",
        "-10.5",
        "kg m/s^2",
        "-10.5 kilogram metre/second^2",
        "-10.5",
        r"\mathrm{kilogram}~\frac{\mathrm{metre}}{\mathrm{second}^{2}}",
        ["FULL_QUANTITY", "NUMBER_VALUE"],
    ),
    (
        "10 kilogram*metre*second**(-2)",
        "10",
        "kilogram*metre*second**(-2)",
        "10 kilogram*metre*second**(-2)",
        "10",
        r"\mathrm{kilogram}\cdot\mathrm{metre}\cdot\mathrm{second}^{-2}",
        ["FULL_QUANTITY", "NUMBER_VALUE"],
    ),
    (
        "10*pi kilogram*metre/second^2",
        "10*pi",
        "kilogram*metre/second^2",
        "10*pi kilogram*metre/second^2",
        r"10 \cdot \pi",
        r"\mathrm{kilogram}\cdot\frac{\mathrm{metre}}{\mathrm{second}^{2}}",
        ["FULL_QUANTITY", "EXPR_VALUE"],
    ),
    (
        "(5.27*pi/sqrt(11) + 5*7)^(4.3)",
        "(5.27*pi/sqrt(11) + 5*7)^(4.3)",
        None,
        "(5.27*pi/sqrt(11) + 5*7)^(4.3)",
        r"\left(\frac{5.27 \cdot \pi}{\sqrt{11}} + 5 \cdot 7\right)^{4.3}",
        None,
        ["NO_UNIT", "EXPR_VALUE"],
    ),
    (
        "(kilogram megametre^2)/(fs^4 daA)",
        None,
        "(kilogram megametre^2)/(fs^4 daA)",
        "(kilogram megametre^2)/(femtosecond^4 decaampere)",
        None,
        r"\frac{\mathrm{kilogram}~\mathrm{megametre}^{2}}{\mathrm{femtosecond}^{4}~\mathrm{decaampere}}",
        ["NO_VALUE"],
    ),
    (
        "(5.27*pi/sqrt(11) + 5*7)^(4.3) (kilogram megametre^2)/(fs^4 daA)",
        "(5.27*pi/sqrt(11) + 5*7)^(4.3)",
        "(kilogram megametre^2)/(fs^4 daA)",
        "(5.27*pi/sqrt(11) + 5*7)^(4.3) (kilogram megametre^2)/(femtosecond^4 decaampere)",
        r"\left(\frac{5.27 \cdot \pi}{\sqrt{11}} + 5 \cdot 7\right)^{4.3}",
        r"\frac{\mathrm{kilogram}~\mathrm{megametre}^{2}}{\mathrm{femtosecond}^{4}~\mathrm{decaampere}}",
        ["FULL_QUANTITY", "EXPR_VALUE"],
    ),
    (
        "(5.27*pi/sqrt(11) + 5*7)^(2+2.3) (kilogram megametre^2)/(fs^4 daA)",
        "(5.27*pi/sqrt(11) + 5*7)^(2+2.3)",
        "(kilogram megametre^2)/(fs^4 daA)",
        "(5.27*pi/sqrt(11) + 5*7)^(2+2.3) (kilogram megametre^2)/(femtosecond^4 decaampere)",
        r"\left(\frac{5.27 \cdot \pi}{\sqrt{11}} + 5 \cdot 7\right)^{2 + 2.3}",
        r"\frac{\mathrm{kilogram}~\mathrm{megametre}^{2}}{\mathrm{femtosecond}^{4}~\mathrm{decaampere}}",
        ["FULL_QUANTITY", "EXPR_VALUE"],
    ),
    (
        "(5*27/11 + 5*7)^(2*3) (kilogram megametre^2)/(fs^4 daA)",
        "(5*27/11 + 5*7)^(2*3)",
        "(kilogram megametre^2)/(fs^4 daA)",
        "(5*27/11 + 5*7)^(2*3) (kilogram megametre^2)/(femtosecond^4 decaampere)",
        r"\left(5 \cdot 27 \cdot \frac{1}{11} + 5 \cdot 7\right)^{2 \cdot 3}",
        r"\frac{\mathrm{kilogram}~\mathrm{megametre}^{2}}{\mathrm{femtosecond}^{4}~\mathrm{decaampere}}",
        ["FULL_QUANTITY", "EXPR_VALUE"],
    ),
    (
        "(pi+10) kg*m/s^2",
        "(pi+10)",
        "kg*m/s^2",
        "(pi+10) kilogram*metre/second^2",
        r"\pi + 10",
        r"\mathrm{kilogram}\cdot\frac{\mathrm{metre}}{\mathrm{second}^{2}}",
        ["FULL_QUANTITY", "EXPR_VALUE"],
    ),
    (
        "10 kilogram*metre/second^2",
        "10",
        "kilogram*metre/second^2",
        "10 kilogram*metre/second^2",
        "10",
        r"\mathrm{kilogram}\cdot\frac{\mathrm{metre}}{\mathrm{second}^{2}}",
        ["FULL_QUANTITY", "NUMBER_VALUE"],
    ),
    (
        "10 kg*m/s^2",
        "10",
        "kg*m/s^2",
        "10 kilogram*metre/second^2",
        "10",
        r"\mathrm{kilogram}\cdot\frac{\mathrm{metre}}{\mathrm{second}^{2}}",
        ["FULL_QUANTITY", "NUMBER_VALUE"],
    ),
    (
        " 10 kg m/s^2 ",
        "10",
        "kg m/s^2",
        "10 kilogram metre/second^2",
        "10",
        r"\mathrm{kilogram}~\frac{\mathrm{metre}}{\mathrm{second}^{2}}",
        ["FULL_QUANTITY", "NUMBER_VALUE"],
    ),
    (
        "10 gram/metresecond",
        "10 gram/metresecond",
        None,
        "10 gram/metresecond",
        r"\frac{10 \cdot e \cdot c \cdot d \cdot gram \cdot n \cdot o}{metres}",
        None,
        ["NO_UNIT", "EXPR_VALUE"],
    ),
    ("10 g/sm", "10 g/sm", None, "10 g/sm", r"\frac{10 \cdot g \cdot m}{s}", None, ["NO_UNIT", "EXPR_VALUE"]),
    (
        "10 s/g + 5 gram*second^2 + 7 ms + 5 gram/second^3",
        "10 s/g + 5 gram*second^2 + 7 ms + 5",
        "gram/second^3",
        "10 s/g + 5 gram*second^2 + 7 ms + 5 gram/second^3",
        r"5 \cdot gram \cdot second^{2} + 7 \cdot m \cdot s + 5 + \frac{10 \cdot s}{g}",
        r"\frac{\mathrm{gram}}{\mathrm{second}^{3}}",
        ["FULL_QUANTITY", "EXPR_VALUE", "REVERTED_UNIT"],
    ),
    (
        "10 kg m/s^2 + 10 kg m/s^2",
        "10 kg m/s^2 + 10",
        "kg m/s^2",
        "10 kg m/s^2 + 10 kilogram metre/second^2",
        r"\frac{10 \cdot g \cdot k \cdot m}{s^{2}} + 10",
        r"\mathrm{kilogram}~\frac{\mathrm{metre}}{\mathrm{second}^{2}}",
        ["FULL_QUANTITY", "EXPR_VALUE", "REVERTED_UNIT"],
    ),
    # ("-0.5 kg m/s^2-10 kg m/s^2",
    # "-0.5 kg m/s^2-10",
    # "kg m/s^2",
    # "-0.5 kg m/s^2-10 kilogram metre/second^2",
    # r"\frac{ -0.5 \cdot g \cdot k cdot m}{s^2} - 10",
    # r"\mathrm{kilogram}~\frac{\mathrm{metre}}{\mathrm{second}^{2}}",
    # ["FULL_QUANTITY", "EXPR_VALUE","REVERTED_UNIT"]),
    (
        "10 second/gram * 7 ms * 5 gram/second",
        "10 second/gram * 7 ms * 5",
        "gram/second",
        "10 second/gram * 7 ms * 5 gram/second",
        r"10 \cdot second \cdot \frac{1}{gram} \cdot 7 \cdot m \cdot s \cdot 5",
        r"\frac{\mathrm{gram}}{\mathrm{second}}",
        ["FULL_QUANTITY", "EXPR_VALUE", "REVERTED_UNIT"],
    ),
    (
        "pi+metre second+pi",
        "pi+metre second+pi",
        None,
        "pi+metre second+pi",
        r"metre \cdot second + \pi + \pi",
        None,
        ["EXPR_VALUE", "NO_UNIT", "REVERTED_UNIT"],
    ),
    ("1/s^2", None, "1/s^2", "1/second^2", None, r"\frac{1}{\mathrm{second}^{2}}", ["NO_VALUE", "HAS_UNIT"]),
    ("5/s^2", "5/s^2", None, "5/s^2", r"\frac{5}{s^{2}}", None, ["NO_UNIT", "EXPR_VALUE", "REVERTED_UNIT"]),
    (
        "10 1/s^2",
        "10",
        "1/s^2",
        "10 1/second^2",
        "10",
        r"\frac{1}{\mathrm{second}^{2}}",
        ["FULL_QUANTITY", "NUMBER_VALUE"],
    ),
]

slr_natural_si_syntax_test_cases = [
    ("fs^4daA", "fs^4daA", None, "fs^4daA", r"A \cdot a \cdot d \cdot f \cdot s^{4}", None, ["NO_UNIT"]),
    (
        "mmPas",
        None,
        "mmPas",
        "millimetre pascal second",
        None,
        r"\mathrm{millimetre}~\mathrm{pascal}~\mathrm{second}",
        ["NO_VALUE", "HAS_UNIT"],
    ),
    (
        "q",  # String that will be used as response / answer
        "q",  # Expected value
        None,  # Expected unit
        "q",  # Content of physical quantity after parsing
        "q",  # Expected LaTeX for value
        None,  # Expected LaTeX for unit
        ["NO_UNIT"],
    ),  # criteria
    ("10", "10", None, "10", "10", None, ["NO_UNIT"]),
    (
        "-10.5*4",
        "-10.5*4",
        None,
        "-10.5*4",
        r"\left(-10.5\right) \cdot 4",  # Ideally parenthesis around -10.5 should be removed here
        None,
        ["NO_UNIT"],
    ),
    ("pi*5", "pi*5", None, "pi*5", r"\pi \cdot 5", None, ["NO_UNIT"]),
    ("5*pi", "5*pi", None, "5*pi", r"5 \cdot \pi", None, ["NO_UNIT"]),
    (
        "sin(-10.5*4)",
        "sin(-10.5*4)",
        None,
        "sin(-10.5*4)",
        r"\sin{\left(\left(-10.5\right) \cdot 4 \right)}",  # Ideally parenthesis around -10.5 should be removed here
        None,
        ["NO_UNIT"],
    ),
    (
        "kilogrammetersecondAmperes",
        None,
        "kilogrammetersecondAmperes",
        "kilogram metre second ampere",
        None,
        r"\mathrm{kilogram}~\mathrm{metre}~\mathrm{second}~\mathrm{ampere}",
        ["NO_VALUE"],
    ),
    (
        "kilogram/(metresecond^2)",
        None,
        "kilogram/(metresecond^2)",
        "kilogram/(metre second^2)",
        None,
        r"\frac{\mathrm{kilogram}}{\mathrm{metre}~\mathrm{second}^{2}}",
        ["NO_VALUE"],
    ),
    (
        "10 kilogram/(metresecond^2)",
        "10",
        "kilogram/(metresecond^2)",
        "10 kilogram/(metre second^2)",
        "10",
        r"\frac{\mathrm{kilogram}}{\mathrm{metre}~\mathrm{second}^{2}}",
        ["FULL_QUANTITY", "NUMBER_VALUE"],
    ),
    (
        "10 kilogrammetre/second**2",
        "10",
        "kilogrammetre/second**2",
        "10 kilogram metre/second**2",
        "10",
        r"\frac{\mathrm{kilogram}~\mathrm{metre}}{\mathrm{second}^{2}}",
        ["FULL_QUANTITY", "NUMBER_VALUE"],
    ),
    (
        "10 kilogrammetre/second^2",
        "10",
        "kilogrammetre/second^2",
        "10 kilogram metre/second^2",
        "10",
        r"\frac{\mathrm{kilogram}~\mathrm{metre}}{\mathrm{second}^{2}}",
        ["FULL_QUANTITY", "NUMBER_VALUE"],
    ),
    (
        "10 kgm/s^2",
        "10",
        "kgm/s^2",
        "10 kilogram metre/second^2",
        "10",
        r"\frac{\mathrm{kilogram}~\mathrm{metre}}{\mathrm{second}^{2}}",
        ["FULL_QUANTITY", "NUMBER_VALUE"],
    ),
    (
        "-10.5 kgm/s^2",
        "-10.5",
        "kgm/s^2",
        "-10.5 kilogram metre/second^2",
        "-10.5",
        r"\frac{\mathrm{kilogram}~\mathrm{metre}}{\mathrm{second}^{2}}",
        ["FULL_QUANTITY", "NUMBER_VALUE"],
    ),
    (
        "10 kilogrammetresecond**(-2)",
        "10",
        "kilogrammetresecond**(-2)",
        "10 kilogram metre second**(-2)",
        "10",
        r"\mathrm{kilogram}~\mathrm{metre}~\mathrm{second}^{-2}",
        ["FULL_QUANTITY", "NUMBER_VALUE"],
    ),
    (
        "10*pi kilogrammetre/second^2",
        "10*pi",
        "kilogrammetre/second^2",
        "10*pi kilogram metre/second^2",
        r"10 \cdot \pi",
        r"\frac{\mathrm{kilogram}~\mathrm{metre}}{\mathrm{second}^{2}}",
        ["FULL_QUANTITY", "EXPR_VALUE"],
    ),
    (
        "(5.27*pi/sqrt(11) + 5*7)^(4.3)",
        "(5.27*pi/sqrt(11) + 5*7)^(4.3)",
        None,
        "(5.27*pi/sqrt(11) + 5*7)^(4.3)",
        r"\left(\frac{5.27 \cdot \pi}{\sqrt{11}} + 5 \cdot 7\right)^{4.3}",
        None,
        ["NO_UNIT", "EXPR_VALUE"],
    ),
    (
        "(kilogrammegametre^2)/(fs^4daA)",
        "(kilogrammegametre^2)/(fs^4daA)",
        None,
        "(kilogrammegametre^2)/(fs^4daA)",
        r"\frac{gram \cdot kilo \cdot mega \cdot metre^{2}}{A \cdot a \cdot d \cdot f \cdot s^{4}}",
        None,
        ["NO_UNIT"],
    ),
    (
        "(5.27*pi/sqrt(11) + 5*7)^(4.3) (kilogrammegametre^2)/(fs^4daA)",
        "(5.27*pi/sqrt(11) + 5*7)^(4.3) (kilogrammegametre^2)/(fs^4daA)",
        None,
        "(5.27*pi/sqrt(11) + 5*7)^(4.3) (kilogrammegametre^2)/(fs^4daA)",
        r"\frac{gram \cdot kilo \cdot mega \cdot metre^{2} \cdot \left(\frac{5.27 \cdot \pi}{\sqrt{11}} + 5 \cdot 7\right)^{4.3}}{A \cdot a \cdot d \cdot f \cdot s^{4}}",
        None,
        ["NO_UNIT"],
    ),
    ("mmg", None, "mmg", "millimetre gram", None, r"\mathrm{millimetre}~\mathrm{gram}", ["ONLY_UNIT"]),
    (
        "(pi+10) kgm/s^2",
        "(pi+10)",
        "kgm/s^2",
        "(pi+10) kilogram metre/second^2",
        r"\pi + 10",
        r"\frac{\mathrm{kilogram}~\mathrm{metre}}{\mathrm{second}^{2}}",
        ["FULL_QUANTITY", "EXPR_VALUE"],
    ),
    (
        "10 gram/metresecond",
        "10",
        "gram/metresecond",
        "10 gram/metre second",
        "10",
        r"\frac{\mathrm{gram}}{\mathrm{metre}~\mathrm{second}}",
        ["FULL_QUANTITY", "NUMBER_VALUE"],
    ),
    (
        "10 g/sm",
        "10",
        "g/sm",
        "10 gram/second metre",
        "10",
        r"\frac{\mathrm{gram}}{\mathrm{second}~\mathrm{metre}}",
        ["FULL_QUANTITY", "NUMBER_VALUE"],
    ),
    (
        "10 s/g + 5 gramsecond^2 + 7 ms + 5 gram/second^3",
        "10 s/g + 5 gramsecond^2 + 7 ms + 5",
        "gram/second^3",
        "10 s/g + 5 gramsecond^2 + 7 ms + 5 gram/second^3",
        r"5 \cdot e \cdot c \cdot d^{2} \cdot grams \cdot n \cdot o + 7 \cdot m \cdot s + 5 + \frac{10 \cdot s}{g}",
        r"\frac{\mathrm{gram}}{\mathrm{second}^{3}}",
        ["FULL_QUANTITY", "EXPR_VALUE", "REVERTED_UNIT"],
    ),
    (
        "10 kgm/s^2 + 10 kgm/s^2",
        "10 kgm/s^2 + 10",
        "kgm/s^2",
        "10 kgm/s^2 + 10 kilogram metre/second^2",
        r"\frac{10 \cdot g \cdot k \cdot m}{s^{2}} + 10",
        r"\frac{\mathrm{kilogram}~\mathrm{metre}}{\mathrm{second}^{2}}",
        ["FULL_QUANTITY", "EXPR_VALUE", "REVERTED_UNIT"],
    ),
    (
        "10 second/gram * 7 ms * 5 gram/second",
        "10 second/gram * 7 ms * 5",
        "gram/second",
        "10 second/gram * 7 ms * 5 gram/second",
        r"10 \cdot second \cdot \frac{1}{gram} \cdot 7 \cdot m \cdot s \cdot 5",
        r"\frac{\mathrm{gram}}{\mathrm{second}}",
        ["FULL_QUANTITY", "EXPR_VALUE", "REVERTED_UNIT"],
    ),
    (
        "pi+metre second+pi",
        "pi+metre second+pi",
        None,
        "pi+metre second+pi",
        r"metre \cdot second + \pi + \pi",
        None,
        ["EXPR_VALUE", "NO_UNIT", "REVERTED_UNIT"],
    ),
    ("1/s^2", None, "1/s^2", "1/second^2", None, r"\frac{1}{\mathrm{second}^{2}}", ["NO_VALUE", "HAS_UNIT"]),
    ("5/s^2", "5/s^2", None, "5/s^2", r"\frac{5}{s^{2}}", None, ["NO_UNIT", "EXPR_VALUE", "REVERTED_UNIT"]),
    (
        "10 1/s^2",
        "10",
        "1/s^2",
        "10 1/second^2",
        "10",
        r"\frac{1}{\mathrm{second}^{2}}",
        ["FULL_QUANTITY", "NUMBER_VALUE"],
    ),
]


class TestEvaluationFunction:
    @pytest.mark.parametrize(
        "string,value,unit,content,value_latex,unit_latex,criteria", slr_strict_si_syntax_test_cases
    )
    def test_strict_si_syntax(self, string, value, unit, content, value_latex, unit_latex, criteria):
        parameters = {**default_parameters}
        parameters.update(
            {
                "strict_syntax": False,
                "units_string": "SI",
                "strictness": "strict",
                "elementary_functions": True,
            }
        )
        quantity = parse_quantity(string, QuantityParams.from_dict(parameters), "quantity")
        parsed_value = quantity.value.original_string() if quantity.value is not None else None
        parsed_unit = quantity.unit.original_string() if quantity.unit is not None else None
        parsed_value_latex = quantity.value_latex
        parsed_unit_latex = quantity.unit_latex
        parsed_content = quantity.ast_root.content_string()
        assert parsed_value == value
        assert parsed_unit == unit
        assert parsed_content == content
        assert parsed_value_latex == value_latex
        assert parsed_unit_latex == unit_latex

    @pytest.mark.parametrize("long_form,short_form", [(u.name, u.symbol) for u in (*SI_BASE_UNITS, *SI_DERIVED_UNITS)])
    def test_short_forms_strict_SI(self, long_form, short_form):
        parameters = {**default_parameters}
        parameters.update({"strict_syntax": False, "units_string": "SI", "strictness": "strict"})
        params = QuantityParams.from_dict(parameters)
        long_quantity = parse_quantity(long_form, params, "quantity")
        short_quantity = parse_quantity(short_form, params, "quantity")
        assert long_quantity.unit.content_string() == short_quantity.unit.content_string()

    @pytest.mark.parametrize(
        "long_form,short_form",
        [(u.name, u.symbol) for u in (*SI_BASE_UNITS, *SI_DERIVED_UNITS, *COMMON_UNITS, *VERY_COMMON_UNITS)],
    )
    def test_short_forms_common_SI(self, long_form, short_form):
        parameters = {**default_parameters}
        parameters.update({"strict_syntax": False, "units_string": "common", "strictness": "strict"})
        params = QuantityParams.from_dict(parameters)
        long_quantity = parse_quantity(long_form, params, "quantity")
        short_quantity = parse_quantity(short_form, params, "quantity")
        assert long_quantity.unit.content_string() == short_quantity.unit.content_string()

    @pytest.mark.parametrize("long_form,short_form", [(u.name, u.symbol) for u in IMPERIAL_UNITS])
    def test_short_forms_imperial(self, long_form, short_form):
        parameters = {**default_parameters}
        parameters.update({"strict_syntax": False, "units_string": "imperial", "strictness": "strict"})
        params = QuantityParams.from_dict(parameters)
        long_quantity = parse_quantity(long_form, params, "quantity")
        short_quantity = parse_quantity(short_form, params, "quantity")
        assert long_quantity.unit.content_string() == short_quantity.unit.content_string()

    @pytest.mark.parametrize(
        "long_form,short_form",
        [
            (u.name, u.symbol)
            for u in (*SI_BASE_UNITS, *SI_DERIVED_UNITS, *COMMON_UNITS, *VERY_COMMON_UNITS, *IMPERIAL_UNITS)
        ],
    )
    def test_short_forms_all(self, long_form, short_form):
        parameters = {**default_parameters}
        parameters.update({"strict_syntax": False, "units_string": "SI common imperial", "strictness": "strict"})
        params = QuantityParams.from_dict(parameters)
        long_quantity = parse_quantity(long_form, params, "quantity")
        short_quantity = parse_quantity(short_form, params, "quantity")
        assert long_quantity.unit.content_string() == short_quantity.unit.content_string()

    @pytest.mark.parametrize(
        "string,value,unit,content,value_latex,unit_latex,criteria", slr_natural_si_syntax_test_cases
    )
    def test_natural_si_syntax(self, string, value, unit, content, value_latex, unit_latex, criteria):
        parameters = {**default_parameters}
        parameters.update(
            {
                "strict_syntax": False,
                "units_string": "SI common imperial",
                "strictness": "natural",
                "elementary_functions": True,
            }
        )
        quantity = parse_quantity(string, QuantityParams.from_dict(parameters), "quantity")
        parsed_unit_latex = quantity.unit_latex
        parsed_value = quantity.value.original_string() if quantity.value is not None else None
        parsed_unit = quantity.unit.original_string() if quantity.unit is not None else None
        parsed_value_latex = quantity.value_latex
        parsed_unit_latex = quantity.unit_latex
        parsed_content = quantity.ast_root.content_string()
        assert parsed_value == value
        assert parsed_unit == unit
        assert parsed_content == content
        assert parsed_value_latex == value_latex
        assert parsed_unit_latex == unit_latex


if __name__ == "__main__":
    pytest.main(["-xs", "--tb=line", os.path.abspath(__file__)])
