from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VERSION_SCRIPT = ROOT / "scripts/packaging/version.py"
VALIDATOR = ROOT / "scripts/packaging/validate-artifacts.py"
VERSION = "0.0.1"
ARTIFACTS = (
    f"LMStudio-Vampire-{VERSION}-linux-x86_64.tar.gz",
    f"LMStudio-Vampire-{VERSION}-linux-x86_64.deb",
    f"LMStudio-Vampire-{VERSION}-macos-x86_64.zip",
    f"LMStudio-Vampire-{VERSION}-windows-x86_64.exe",
    f"LMStudio-Vampire-{VERSION}-windows-x86_64-portable.zip",
)


def run_script(script: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_version_metadata_and_tag_agree() -> None:
    result = run_script(VERSION_SCRIPT, "--tag", f"v{VERSION}")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == VERSION


def test_version_rejects_mismatched_tag() -> None:
    result = run_script(VERSION_SCRIPT, "--tag", "v9.9.9")
    assert result.returncode != 0
    assert "does not match" in result.stderr


def test_release_artifacts_and_checksums(tmp_path: Path) -> None:
    for name in ARTIFACTS:
        (tmp_path / name).write_bytes(name.encode())

    result = run_script(
        VALIDATOR,
        str(tmp_path),
        "--version",
        VERSION,
        "--write-checksums",
    )
    assert result.returncode == 0, result.stderr
    manifest = (tmp_path / "SHA256SUMS.txt").read_text(encoding="utf-8")
    assert all(name in manifest for name in ARTIFACTS)

    (tmp_path / ARTIFACTS[0]).write_bytes(b"changed")
    result = run_script(VALIDATOR, str(tmp_path), "--version", VERSION)
    assert result.returncode != 0
    assert "checksum mismatch" in result.stderr


@pytest.mark.parametrize("platform", ("linux", "macos", "windows"))
def test_platform_validation_rejects_missing_artifacts(tmp_path: Path, platform: str) -> None:
    result = run_script(
        VALIDATOR,
        str(tmp_path),
        "--version",
        VERSION,
        "--platform",
        platform,
    )
    assert result.returncode != 0
    assert "missing or empty artifacts" in result.stderr
