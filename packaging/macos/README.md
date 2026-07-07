# macOS packaging

Builds the macOS application bundle, `LM Studio Vampire.app`, from the same
Python package using PyInstaller.

> PyInstaller is **not** a cross-compiler — build this on macOS.

## Build

```bash
scripts/packaging/build-macos.sh
```

The script upgrades `pip`, installs the package, installs `pyinstaller`, and runs
`pyinstaller packaging/macos/LMStudioVampire.spec`. The bundle is written to
`dist/LM Studio Vampire.app`.

## Files in this folder

| File | Purpose |
| --- | --- |
| [`LMStudioVampire.spec`](LMStudioVampire.spec) | PyInstaller recipe. Targets `src/vampire/desktop/launcher.py`, bundles `assets/vampire-dashboard.html`, collects all `vampire` submodules, and emits a windowed `.app` via `BUNDLE(...)`. |
| [`Info.plist`](Info.plist) | Bundle metadata: name, identifier `technology.japer.lmstudio-vampire`, version, and `LSMinimumSystemVersion` 12.0. |
| [`entitlements.plist`](entitlements.plist) | Sandbox entitlements granting network client + server access (the gateway both makes outbound calls and listens locally). |

## What the bundle does

Launching the app runs `vampire-desktop`, which starts the gateway (default
`127.0.0.1:7777`) and opens the bundled dashboard in the default browser. The
proxied LM Studio node defaults to `http://localhost:1234` and can be overridden
with `VAMPIRE_*` environment variables or a `.env` file.

## Signing & notarization

Release builds must be code-signed and notarized before distribution:

- Set `codesign_identity` (and, if needed, `target_arch`) in the spec, or sign
  the produced `.app` with `codesign` afterward using the entitlements here.
- Notarize with `notarytool` and staple the ticket.

Keep signing credentials out of the repository; store them in CI secrets. See
[`../common/release-metadata/`](../common/release-metadata/) for signing metadata
templates.

## Verify

Run [`../common/smoke-test.md`](../common/smoke-test.md) against the built `.app`
on a clean machine before publishing.
