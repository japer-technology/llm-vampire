# Building and releasing LLM Vampire

LLM Vampire is a Python 3.10+ application with two entry points:
`vampire` for the CLI and `vampire-desktop` for the browser-opening desktop
launcher. Release packages contain the desktop launcher and its Python runtime.
PyInstaller builds are native and cannot be cross-compiled.

## Supported release targets

The automated release currently supports x86-64 runners only:

| Target | Release files |
| --- | --- |
| Linux x86-64 | `.tar.gz` standalone archive and Debian/Ubuntu `.deb` |
| macOS 12+ x86-64 | ZIP containing `LLM Vampire.app` |
| Windows x86-64 | portable ZIP and Inno Setup `.exe` installer |

AppImage, RPM, MSI, 32-bit, and ARM releases are not implemented. The source is
portable Python, but those release packages have not been validated. The HTML
helper applications under `packaging/html/` are supporting tools and are not
LLM Vampire release assets.

## Prerequisites

All platforms require Git, Python 3.12 for release parity, and
[`uv` 0.11.28](https://docs.astral.sh/uv/). From a clean checkout:

```bash
uv sync --frozen --extra dev --extra packaging
uv run python scripts/packaging/version.py
```

Linux also requires GNU `tar` and `dpkg-deb`. macOS requires Xcode command-line
tools and `ditto`. Windows requires PowerShell and Inno Setup 6 at its default
installation path.

## Build and test locally

Run the same quality gates as CI:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
```

Build the Python wheel and source distribution when needed:

```bash
uv build
```

The wheel and source distribution appear in `dist/`; they are not GitHub Release
assets.

## Package locally

Run the command matching the host operating system from the repository root.

Linux:

```bash
scripts/packaging/build-linux.sh
scripts/packaging/build-ubuntu-deb.sh
```

macOS:

```bash
scripts/packaging/build-macos.sh
```

Windows PowerShell:

```powershell
.\scripts\packaging\build-windows.ps1
```

Artifacts appear in `dist/` with names beginning
`LLM-Vampire-<version>-<platform>-<architecture>`. Linux and Debian builds
may be run independently; the Debian script always performs a clean Linux build.
CI may pass `--reuse-linux-build` only after building Linux in the same job.

To validate a complete set and create checksums:

```bash
uv run python scripts/packaging/validate-artifacts.py \
  dist --version 0.0.1 --write-checksums
```

The validator requires every expected file to exist, be non-empty, have the
canonical name, and be listed exactly once in `SHA256SUMS.txt`.

## Versioning

Release tags use strict `vX.Y.Z` semantic versions. `pyproject.toml`,
`src/vampire/__init__.py`, and `VERSION` contain package metadata that is
validated against the tag before any build starts. Update all three in the same
commit when preparing a new version; installer and bundle metadata are injected
from the validated tag during packaging.

## GitHub Releases

`.github/workflows/packaging.yml` runs for tags matching `v*.*.*`. It validates
the tag and source, builds each native target, checks expected outputs, creates
one GitHub Release with the repository-provided `GITHUB_TOKEN`, and uploads each
package plus `SHA256SUMS.txt` as separate assets.

Test all jobs without creating a release from **Actions → Build and release →
Run workflow**. Enter the version currently present in project metadata. Manual
runs upload workflow artifacts only; only a tag-push run can publish a GitHub
Release.

To publish after the draft pull request is merged and version metadata is ready:

```bash
git switch main
git pull --ff-only
git tag -a v0.0.1 -m "LLM Vampire v0.0.1"
git push origin v0.0.1
```

Do not create the tag until the commit containing the matching version metadata
is on the intended release branch.

## Signing limitations

Current packages are unsigned and the macOS app is not notarized. macOS
Gatekeeper and Windows SmartScreen may therefore warn users. Unsigned builds
remain fully buildable.

The following repository secret names are reserved for a future signing step:

- `WINDOWS_SIGNING_CERTIFICATE_BASE64`
- `WINDOWS_SIGNING_CERTIFICATE_PASSWORD`
- `MACOS_SIGNING_CERTIFICATE_BASE64`
- `MACOS_SIGNING_CERTIFICATE_PASSWORD`
- `MACOS_SIGNING_IDENTITY`
- `MACOS_NOTARY_APPLE_ID`
- `MACOS_NOTARY_TEAM_ID`
- `MACOS_NOTARY_PASSWORD`

Never commit certificates, private keys, passwords, or notarization credentials.
Signing must occur before checksum generation and asset upload.
