# Packaging

This directory holds everything needed to turn the `lmstudio-vampire` Python
package into installable, distributable artifacts for each supported platform.

LM Studio Vampire is the product: a private AI compute gateway that fronts
owner-approved LM Studio API endpoints and serves a bundled dashboard. Packaging
wraps the same Python package around the `vampire-desktop` launcher
(`vampire.desktop.launcher:main`) so end users can install and run it without a
Python toolchain.

## Layout

| Path | Purpose |
| --- | --- |
| [`common/`](common/) | Cross-platform packaging assets and the shared smoke test. |
| [`html/`](html/) | Self-contained single-file HTML/JS/CSS helper apps. |
| [`common/icons/`](common/icons/) | Generated platform icon files (`.ico`, `.icns`, `.png`). |
| [`common/release-metadata/`](common/release-metadata/) | Shared release notes, signing, and store metadata templates. |
| [`linux/`](linux/) | Generic (non-Ubuntu) Linux artifacts: source rebuilds, wheels, sdists. |
| [`linux/appimage/`](linux/appimage/) | AppImage build recipes and metadata. |
| [`macos/`](macos/) | macOS `.app` bundle: PyInstaller spec, `Info.plist`, entitlements. |
| [`ubuntu/`](ubuntu/) | Debian/Ubuntu `.deb` metadata and desktop integration. |
| [`ubuntu/debian/`](ubuntu/debian/) | Debian control files for `dpkg-buildpackage`. |
| [`windows/`](windows/) | Windows `.exe` PyInstaller spec and Inno Setup installer. |

## Build scripts

Per-platform build scripts live in [`scripts/packaging/`](../scripts/packaging/)
and are invoked from the repository root:

| Platform | Script | Output |
| --- | --- | --- |
| Linux (source) | `scripts/packaging/build-linux-source.sh` | wheel + sdist in `dist/` |
| Ubuntu (`.deb`) | `scripts/packaging/build-ubuntu-deb.sh` | wheel + sdist (`.deb` recipe WIP) |
| macOS (`.app`) | `scripts/packaging/build-macos.sh` | `dist/LM Studio Vampire.app` |
| Windows (`.exe`) | `scripts/packaging/build-windows.ps1` | `dist/LMStudioVampire/` |
| HTML apps | `scripts/packaging/build-html-apps.sh` | single-file apps in `dist/html/` |

PyInstaller is **not** a cross-compiler: build each native artifact on the
platform it targets (macOS on macOS, Windows on Windows).

## Entry points

Both packaged and source installs expose two console scripts (see
[`pyproject.toml`](../pyproject.toml)):

- `vampire` — the CLI (`vampire.cli:main`).
- `vampire-desktop` — the double-click launcher (`vampire.desktop.launcher:main`)
  that starts the gateway and opens the dashboard in a browser.

## Runtime defaults

The gateway binds `127.0.0.1:7777` by default and proxies to a downstream LM
Studio node at `http://localhost:1234`. Settings are read from defaults, a
`.env` file, and `VAMPIRE_`-prefixed environment variables
(`VAMPIRE_HOST`, `VAMPIRE_PORT`, `VAMPIRE_LMSTUDIO_BASE_URL`,
`VAMPIRE_LOG_LEVEL`, `VAMPIRE_AUTH_TOKEN`).

## Verifying a build

After producing any artifact, follow [`common/smoke-test.md`](common/smoke-test.md)
on a clean machine or VM for that platform before publishing a release.
