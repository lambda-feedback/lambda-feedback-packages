"""Diff the current packages against the v0.1 parity baseline.

    poetry run python tools/parity/check.py            # report, exit 1 on unexpected diffs
    poetry run python tools/parity/check.py --update   # also record current values of
                                                       # already-listed expected changes
    poetry run python tools/parity/check.py --accept "why"   # record every unexpected diff as
                                                             # an expected change (review first!)

Probes mirror ``capture_v0_1.py`` key-for-key; only the calls into the
packages are adapted as their APIs change during the refactor. Intentional
behaviour changes (bug fixes) are listed in ``expected_changes.json`` as
``{key: {"reason": ..., "value": <new output>}}`` and must match exactly.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import warnings
from copy import deepcopy
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
warnings.simplefilter("ignore")

from corpus import (  # noqa: E402
    CRITERIA_STRINGS,
    EXPRESSION_INPUTS,
    EXPRESSION_VARIANTS,
    QUANTITY_INPUTS,
    QUANTITY_VARIANTS,
)

from lambdafeedback.criteria import build_criteria_parser  # noqa: E402
from lambdafeedback.expression_parsing import (  # noqa: E402
    ExpressionParams,
    SympyParsingConfig,
    parse_expressions,
    sympy_to_latex,
)
from lambdafeedback.units import QuantityParams, parse_quantity  # noqa: E402

ERROR = "ERROR"


def probe(fn: Any, *args: Any) -> Any:
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            return fn(*args)
        except Exception:
            return ERROR


# --- Adapters: the only part that changes as the package APIs change. ---


def criteria_tree(criterion: str) -> str:
    reserved = {"learner": {"response": "a*b*c"}, "task": {"answer": "c*b*a"}}
    parser = build_criteria_parser(reserved)
    return parser.parse(parser.scan(criterion))[0].tree_string()


def expression_params(variant: str) -> dict[str, Any]:
    return deepcopy(EXPRESSION_VARIANTS[variant])


def expression_parse(expr: str, variant: str) -> dict[str, Any]:
    params = ExpressionParams.from_dict(expression_params(variant))
    parsed = parse_expressions(expr, SympyParsingConfig.from_params(params))
    if len(parsed) > 1:
        return {"parsed": sorted(str(p) for p in parsed)}
    return {"parsed": str(parsed[0]), "latex": sympy_to_latex(parsed[0], params.symbols)}


def quantity_params(variant: str) -> dict[str, Any]:
    params: dict[str, Any] = {"physical_quantity": True, "strictness": "natural", "units_string": "SI common imperial"}
    params.update(deepcopy(QUANTITY_VARIANTS[variant]))
    return params


def quantity_parse(expr: str, variant: str) -> dict[str, Any]:
    params = QuantityParams.from_dict(quantity_params(variant))
    q = parse_quantity(expr, params, "response")

    def s(x: Any) -> str | None:
        return None if x is None else str(x)

    # v0.1 gave one expression, or a set of several.
    values = q.standard_values
    standard_value = None if values is None else values[0] if len(values) == 1 else set(values)

    return {
        "value": None if q.value is None else q.value.original_string(),
        "unit": None if q.unit is None else q.unit.original_string(),
        "content": q.ast_root.content_string(),
        "value_latex": q.value_latex,
        "unit_latex": q.unit_latex,
        "latex": q.latex,
        "standard_value": s(standard_value),
        "standard_unit": s(q.standard_unit),
        "expanded_unit": s(q.expanded_unit),
        "dimension": s(q.dimension),
        "unit_factor": s(q.unit_factor),
        "messages": [{"before": r.before, "marked": r.marked, "after": r.after} for r in q.reverted_units],
    }


# --- Probe layout: must stay key-for-key identical to capture_v0_1.py. ---


def collect() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for criterion in CRITERIA_STRINGS:
        out[f"criteria.parse|{criterion}"] = probe(criteria_tree, criterion)
    for variant in EXPRESSION_VARIANTS:
        for expr in EXPRESSION_INPUTS:
            out[f"expr.parse|{variant}|{expr}"] = probe(expression_parse, expr, variant)
    for variant in QUANTITY_VARIANTS:
        for expr in QUANTITY_INPUTS:
            out[f"quantity.parse|{variant}|{expr}"] = probe(quantity_parse, expr, variant)
    return out


def main() -> int:
    update = "--update" in sys.argv
    baseline = json.loads((HERE / "baseline.json").read_text(encoding="utf-8"))
    expected_path = HERE / "expected_changes.json"
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    # Round-trip through JSON so tuples/lists compare the same way as the baseline.
    current = json.loads(json.dumps(collect(), ensure_ascii=False))

    if set(current) != set(baseline):
        print("Probe keys differ from baseline:", sorted(set(current) ^ set(baseline))[:10])
        return 1

    unexpected = [k for k in current if current[k] != baseline[k] and k not in expected]
    wrong = [k for k in expected if current[k] != expected[k]["value"]]

    for k in unexpected:
        print(f"UNEXPECTED {k}\n  baseline: {baseline[k]}\n  current:  {current[k]}")
    for k in wrong:
        print(f"MISMATCH (expected change) {k}\n  expected: {expected[k]['value']}\n  current:  {current[k]}")
        if update:
            expected[k]["value"] = current[k]

    accept_reason = sys.argv[sys.argv.index("--accept") + 1] if "--accept" in sys.argv else None
    if accept_reason:
        for k in unexpected:
            expected[k] = {"reason": accept_reason, "value": current[k]}
        print(f"Accepted {len(unexpected)} change(s) as expected.")
        unexpected = []

    if (update and wrong) or accept_reason:
        expected_path.write_text(json.dumps(expected, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
        if update and wrong:
            print(f"Updated {len(wrong)} expected value(s).")

    print(
        f"{len(current)} probes; {len(expected)} expected changes; "
        f"{len(unexpected)} unexpected; {len(wrong)} mismatched"
    )
    return 1 if unexpected or (wrong and not update) else 0


if __name__ == "__main__":
    sys.exit(main())
