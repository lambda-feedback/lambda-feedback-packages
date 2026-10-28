"""Check a release tag against the packages' versions before building a release.

    python scripts/release_version.py v0.4.0            # a stable release
    python scripts/release_version.py v0.4.0-rc.1 --prerelease

Tags are semantic versions: ``vMAJOR.MINOR.PATCH`` for a release, and
``vMAJOR.MINOR.PATCH-alpha.N`` / ``-beta.N`` / ``-rc.N`` for a pre-release.
Python versions spell pre-releases differently (PEP 440), so ``v0.4.0-rc.1``
expects ``version = "0.4.0rc1"`` in each ``pyproject.toml``.

Checks that the tag is the kind asked for, that all four packages declare its
version (they share one), and that every dependency range between the
packages admits it: ``>=0.4.0,<0.5.0`` does not admit ``0.4.0rc1``, so a
pre-release needs ``>=0.4.0rc1,<0.5.0``.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = ("slr_parsing", "criteria", "expression_parsing", "physical_quantities")
# Semantic-version pre-release labels and their PEP 440 spellings, in release order.
PRE_RELEASE_LABELS = {"alpha": "a", "beta": "b", "rc": "rc"}


class Version(NamedTuple):
    """A version as both kinds of tag spell it; compares in release order."""

    release: tuple[int, int, int]
    stage: int  # index in PRE_RELEASE_LABELS, or len(PRE_RELEASE_LABELS) for a final release
    number: int

    @property
    def is_prerelease(self) -> bool:
        return self.stage < len(PRE_RELEASE_LABELS)

    def pep440(self) -> str:
        core = ".".join(map(str, self.release))
        if not self.is_prerelease:
            return core
        return f"{core}{list(PRE_RELEASE_LABELS.values())[self.stage]}{self.number}"


def _release(text: str) -> tuple[int, int, int]:
    parts = text.split(".")
    if len(parts) != 3 or not all(part.isdecimal() for part in parts):
        raise ValueError(f"{text!r} is not MAJOR.MINOR.PATCH")
    major, minor, patch = (int(part) for part in parts)
    return major, minor, patch


def parse_tag(tag: str) -> Version:
    """``v0.4.0`` or ``v0.4.0-rc.1`` (semantic versioning, with a leading ``v``)."""
    if not tag.startswith("v"):
        raise ValueError(f"Tag {tag!r} must start with 'v'")
    core, _, pre = tag[1:].partition("-")
    if not pre:
        return Version(_release(core), len(PRE_RELEASE_LABELS), 0)
    label, _, number = pre.partition(".")
    if label not in PRE_RELEASE_LABELS or not number.isdecimal():
        raise ValueError(f"Pre-release {pre!r} must be alpha.N, beta.N or rc.N")
    return Version(_release(core), list(PRE_RELEASE_LABELS).index(label), int(number))


def parse_pep440(text: str) -> Version:
    """``0.4.0`` or ``0.4.0rc1`` (also ``a1``/``b1``), as in ``pyproject.toml``."""
    for stage, suffix in sorted(enumerate(PRE_RELEASE_LABELS.values()), key=lambda item: -len(item[1])):
        core, found, number = text.partition(suffix)
        if found and number.isdecimal():
            return Version(_release(core), stage, int(number))
    return Version(_release(text), len(PRE_RELEASE_LABELS), 0)


def sibling_ranges(project: dict[str, object]) -> list[tuple[str, Version, Version]]:
    """``(name, lower, upper)`` for each ``lambdafeedback-*`` requirement written ``name (>=lower,<upper)``."""
    ranges = []
    dependencies = project.get("dependencies", [])
    assert isinstance(dependencies, list)
    for requirement in dependencies:
        name, _, spec = str(requirement).partition(" (")
        if not name.startswith("lambdafeedback-"):
            continue
        lower = upper = None
        for bound in spec.rstrip(")").split(","):
            bound = bound.strip()
            if bound.startswith(">="):
                lower = bound[2:]
            elif bound.startswith("<"):
                upper = bound[1:]
        if lower is None or upper is None:
            raise ValueError(f"{requirement!r} must be written 'name (>=lower,<upper)'")
        ranges.append((name, parse_pep440(lower), parse_pep440(upper)))
    return ranges


def problems(tag: Version, prerelease: bool) -> list[str]:
    found = []
    if tag.is_prerelease != prerelease:
        kind = "a pre-release" if prerelease else "a release"
        found.append(
            f"this pipeline builds {kind}, but the tag is {'a pre-release' if tag.is_prerelease else 'a release'}"
        )
    for package in PACKAGES:
        project = tomllib.loads((ROOT / package / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        declared = parse_pep440(project["version"])
        if declared != tag:
            found.append(f"{package}/pyproject.toml has version {project['version']}, the tag needs {tag.pep440()}")
        for name, lower, upper in sibling_ranges(project):
            if not lower <= tag < upper:
                found.append(
                    f"{package} requires {name} >={lower.pep440()},<{upper.pep440()}, which excludes {tag.pep440()}"
                )
    return found


def main() -> int:
    arguments = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    arguments.add_argument("tag", help="the release tag, e.g. v0.4.0 or v0.4.0-rc.1")
    arguments.add_argument("--prerelease", action="store_true", help="the tag must be a pre-release")
    options = arguments.parse_args()
    try:
        tag = parse_tag(options.tag)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    if found := problems(tag, options.prerelease):
        print("\n".join(found), file=sys.stderr)
        return 1
    print(f"{options.tag}: all packages are at {tag.pep440()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
