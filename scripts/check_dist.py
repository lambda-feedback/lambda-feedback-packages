"""Build every package and check the artefacts are fit to publish.

    poetry run python scripts/check_dist.py [--out DIR]

For each package: build the wheel and sdist, check the wheel holds only its
``lambdafeedback/<package>`` namespace portion (no ``lambdafeedback/__init__.py``,
which would break the namespace) and ``py.typed``, that its requirements are
the published ones (no development path dependencies), and that the sdist
carries the tests, changelog and licence. Then install all four wheels into a
fresh virtual environment and run a smoke test through every package.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = ("slr_parsing", "criteria", "expression_parsing", "units")

SMOKE_TEST = """
from lambdafeedback.criteria import build_criteria_parser
from lambdafeedback.expression_parsing import ExpressionParams, SympyParsingConfig, parse_expression
from lambdafeedback.units import QuantityParams, parse_quantity
from lambdafeedback.slr_parsing import SLRParser

assert str(parse_expression("2x+1", SympyParsingConfig.from_params(ExpressionParams()))) == "2*x + 1"
assert parse_quantity("9.81 m/s^2", QuantityParams()).unit.content_string() == "metre/second^2"
parser = build_criteria_parser({"learner": {"response": None}})
assert isinstance(parser, SLRParser)
print("smoke test passed")
"""


def check_wheel(wheel: Path, package: str) -> list[str]:
    problems = []
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        metadata = archive.read(next(name for name in names if name.endswith(".dist-info/METADATA"))).decode()
    portion = f"lambdafeedback/{package}/"
    code = [name for name in names if not name.split("/")[0].endswith(".dist-info")]
    if "lambdafeedback/__init__.py" in names:
        problems.append("ships lambdafeedback/__init__.py, which breaks the namespace package")
    if stray := [name for name in code if not name.startswith(portion)]:
        problems.append(f"files outside {portion}: {stray}")
    if f"{portion}py.typed" not in names:
        problems.append("no py.typed")
    requirements = [line for line in metadata.splitlines() if line.startswith("Requires-Dist:")]
    if local := [line for line in requirements if "@ file:" in line or "develop" in line]:
        problems.append(f"requirements point at local paths: {local}")
    return problems


def check_sdist(sdist: Path) -> list[str]:
    with tarfile.open(sdist) as archive:
        names = archive.getnames()
    wanted = {"tests": "/tests/", "changelog": "/CHANGELOG.md", "licence": "/LICENSE"}
    return [f"sdist has no {what}" for what, part in wanted.items() if not any(part in name for name in names)]


def main() -> int:
    arguments = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    arguments.add_argument("--out", type=Path, help="where to build (default: a temporary directory)")
    out = arguments.parse_args().out or Path(tempfile.mkdtemp(prefix="lambdafeedback-dist-"))
    out.mkdir(parents=True, exist_ok=True)

    problems: dict[str, list[str]] = {}
    for package in PACKAGES:
        target = out / package
        subprocess.run(["poetry", "build", "--quiet", "--output", str(target)], cwd=ROOT / package, check=True)
        [wheel] = target.glob("*.whl")
        [sdist] = target.glob("*.tar.gz")
        problems[package] = check_wheel(wheel, package) + check_sdist(sdist)

    environment = out / "venv"
    venv.create(environment, with_pip=True)
    python = environment / ("Scripts" if sys.platform == "win32" else "bin") / "python"
    wheels = [str(next((out / package).glob("*.whl"))) for package in PACKAGES]
    subprocess.run([str(python), "-m", "pip", "install", "--quiet", "--disable-pip-version-check", *wheels], check=True)
    smoke = subprocess.run([str(python), "-c", SMOKE_TEST], capture_output=True, text=True)
    if smoke.returncode != 0:
        problems["installed wheels"] = [smoke.stderr.strip().splitlines()[-1]]

    for package, found in problems.items():
        for problem in found:
            print(f"{package}: {problem}")
    if any(problems.values()):
        return 1
    print(f"All {len(PACKAGES)} packages build cleanly; artefacts in {out}")
    print(smoke.stdout.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
