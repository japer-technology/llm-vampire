# Windows packaging

Builds the native Windows application from the same Python package using
PyInstaller, and wraps it in an Inno Setup installer.

> PyInstaller is **not** a cross-compiler — build this on Windows.

## Build

```powershell
.\scripts\packaging\build-windows.ps1
```

The script upgrades `pip`, installs the package, installs `pyinstaller`, and runs
`pyinstaller packaging/windows/LMStudioVampire.spec`. The onedir build is written
to `dist/LMStudioVampire/`.

## Files in this folder

| File | Purpose |
| --- | --- |
| [`LMStudioVampire.spec`](LMStudioVampire.spec) | PyInstaller recipe. Targets `src/vampire/desktop/launcher.py`, bundles `assets/vampire-dashboard.html`, collects all `vampire` submodules, and emits `LMStudioVampire.exe` (currently `console=True`). |
| [`installer.iss`](installer.iss) | Inno Setup script that packages the `dist/LMStudioVampire/` onedir output into `LMStudioVampireSetup.exe`, installing to Program Files and creating Start Menu + desktop shortcuts. |

## What the executable does

Running `LMStudioVampire.exe` starts `vampire-desktop`, which launches the
gateway (default `127.0.0.1:7777`) and opens the bundled dashboard in the default
browser. The proxied LM Studio node defaults to `http://localhost:1234` and can
be overridden with `VAMPIRE_*` environment variables or a `.env` file.

## Building the installer

After the PyInstaller build produces `dist/LMStudioVampire/`, compile the
installer with Inno Setup:

```powershell
iscc packaging\windows\installer.iss
```

Keep the `AppVersion` in `installer.iss` in sync with
[`pyproject.toml`](../../pyproject.toml) (currently `0.0.1`). To ship a
windowed (non-console) app, set `console=False` in the spec and wire an icon from
[`../common/icons/`](../common/icons/).

## Signing

Release executables and installers should be Authenticode-signed with
`signtool`. Keep certificates and passwords in CI secrets, never in the repo.

## Verify

Run [`../common/smoke-test.md`](../common/smoke-test.md) against the installed app
on a clean Windows machine before publishing.
