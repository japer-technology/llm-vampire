#!/usr/bin/env python3
"""Create and validate the checksum manifest for release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

PLATFORM_ARTIFACTS = {
    "linux": (
        "LLM-Vampire-{version}-linux-x86_64.tar.gz",
        "LLM-Vampire-{version}-linux-x86_64.deb",
    ),
    "macos": ("LLM-Vampire-{version}-macos-x86_64.zip",),
    "windows": (
        "LLM-Vampire-{version}-windows-x86_64.exe",
        "LLM-Vampire-{version}-windows-x86_64-portable.zip",
    ),
}


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def expected_names(version: str, platform: str) -> set[str]:
    platforms = (
        PLATFORM_ARTIFACTS if platform == "all" else {platform: PLATFORM_ARTIFACTS[platform]}
    )
    return {
        template.format(version=version)
        for templates in platforms.values()
        for template in templates
    }


def validate_artifacts(directory: Path, version: str, platform: str) -> list[Path]:
    names = expected_names(version, platform)
    artifacts = [directory / name for name in sorted(names)]
    missing = [path.name for path in artifacts if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise ValueError(f"missing or empty artifacts: {', '.join(missing)}")
    return artifacts


def write_checksums(directory: Path, artifacts: list[Path]) -> Path:
    manifest = directory / "SHA256SUMS.txt"
    manifest.write_text(
        "".join(f"{digest(path)}  {path.name}\n" for path in artifacts),
        encoding="utf-8",
    )
    return manifest


def verify_checksums(directory: Path, artifacts: list[Path]) -> None:
    manifest = directory / "SHA256SUMS.txt"
    if not manifest.is_file() or manifest.stat().st_size == 0:
        raise ValueError("SHA256SUMS.txt is missing or empty")
    entries: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([^/]+)", line)
        if match is None:
            raise ValueError(f"invalid checksum line: {line!r}")
        entries[match.group(2)] = match.group(1)
    expected = {path.name for path in artifacts}
    if set(entries) != expected:
        raise ValueError("checksum manifest does not list exactly the expected artifacts")
    mismatched = [path.name for path in artifacts if entries[path.name] != digest(path)]
    if mismatched:
        raise ValueError(f"checksum mismatch: {', '.join(mismatched)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--platform", choices=(*PLATFORM_ARTIFACTS, "all"), default="all")
    parser.add_argument("--write-checksums", action="store_true")
    args = parser.parse_args()
    try:
        artifacts = validate_artifacts(args.directory, args.version, args.platform)
        if args.write_checksums:
            write_checksums(args.directory, artifacts)
        if args.platform == "all":
            verify_checksums(args.directory, artifacts)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"Validated {len(artifacts)} release artifact(s) in {args.directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
