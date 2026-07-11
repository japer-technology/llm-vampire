#!/usr/bin/env python3
"""Resolve and validate the release version used by packaging scripts."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[2]
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def metadata_versions() -> tuple[str, str, str]:
    with (ROOT / "pyproject.toml").open("rb") as file:
        project_version = str(tomllib.load(file)["project"]["version"])

    package_text = (ROOT / "src/vampire/__init__.py").read_text(encoding="utf-8")
    package_match = re.search(r'^__version__ = "([^"]+)"$', package_text, re.MULTILINE)
    if package_match is None:
        raise ValueError("src/vampire/__init__.py does not define __version__")

    version_file = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    return project_version, package_match.group(1), version_file


def exact_git_tag() -> str | None:
    result = subprocess.run(
        ["git", "describe", "--tags", "--exact-match", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def resolve_version(tag: str | None = None) -> str:
    project_version, package_version, version_file = metadata_versions()
    versions = {
        "pyproject.toml": project_version,
        "src/vampire/__init__.py": package_version,
        "VERSION": version_file,
    }
    invalid = {name: value for name, value in versions.items() if not SEMVER.fullmatch(value)}
    if invalid:
        details = ", ".join(f"{name}={value!r}" for name, value in invalid.items())
        raise ValueError(f"versions must use X.Y.Z format: {details}")
    if len(set(versions.values())) != 1:
        details = ", ".join(f"{name}={value}" for name, value in versions.items())
        raise ValueError(f"version metadata disagrees: {details}")

    release_tag = tag or exact_git_tag()
    if release_tag is not None:
        if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", release_tag):
            raise ValueError(f"release tag must use vX.Y.Z format: {release_tag!r}")
        if release_tag[1:] != project_version:
            raise ValueError(
                f"release tag {release_tag!r} does not match project version {project_version!r}"
            )
    return project_version


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", help="release tag to validate, for example v1.2.3")
    args = parser.parse_args()
    try:
        print(resolve_version(args.tag))
    except (OSError, KeyError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
