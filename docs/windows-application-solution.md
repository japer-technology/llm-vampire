# Windows Application Solution

> How to compile `llm-vampire` into a standalone Windows executable (`.exe`)
> that an owner can double-click to turn their PC into an LLM Vampire — no
> Python install, no `pip`, no command line required.

This document explains **what is required** to ship a distributable Windows `.exe`,
the **changes the codebase needs** to be freeze-friendly, a **recommended build
recipe**, and the **trade-offs** between the available tools. It is a planning and
reference document; it does not, by itself, add a build to the repository.

---

## 1. What we are actually packaging

Vampire is a pure-Python project (see [`pyproject.toml`](../pyproject.toml)):

- **Language / runtime:** Python `>=3.10`.
- **Entry point:** the `vampire` console script → `vampire.cli:main`
  ([`src/vampire/cli.py`](../src/vampire/cli.py)). The interesting subcommand is
  `vampire serve`, which starts a Uvicorn/ASGI server.
- **Web server:** `vampire serve` calls
  `uvicorn.run(create_app(), ...)`
  ([`src/vampire/cli.py`](../src/vampire/cli.py)). The app factory lives in
  [`src/vampire/app.py`](../src/vampire/app.py).
- **Runtime dependencies:** `fastapi`, `uvicorn`, `httpx`, `pydantic`,
  `pydantic-settings`, `zeroconf`, `aiosqlite`.
- **Bundled data:** the single-file Phase 4 dashboard
  [`src/vampire/assets/vampire-dashboard.html`](../src/vampire/assets/vampire-dashboard.html), served at `/`
  by `create_app()` via a `FileResponse` route.

So "compile to an exe" means: **bundle the CPython interpreter, all of the above
dependencies, and the `src/vampire/assets/vampire-dashboard.html` asset into a single self-contained Windows binary**
that, when run, starts the gateway and (optionally) opens the dashboard in a
browser.

There is no C/C++ to "compile" in the traditional sense. Tools like PyInstaller
**freeze** the app (interpreter + bytecode + data) into an `.exe`; Nuitka can
genuinely **compile** Python to C for extra speed/obfuscation. Both produce a
runnable `.exe`.

---

## 2. Recommended approach: PyInstaller

PyInstaller is the most widely used, best-supported option for this exact shape
of app (FastAPI + Uvicorn + Pydantic v2). It already has community hooks for the
tricky dependencies, and it runs natively on the GitHub-hosted `windows-latest`
runner so we can build in CI without owning a Windows machine.

### 2.1 Prerequisites

- A **Windows** build host (PyInstaller is **not** a cross-compiler — you must
  build the Windows `.exe` *on* Windows; use a Windows machine, a Windows VM, or
  a `windows-latest` GitHub Actions runner).
- Python 3.10+ for Windows (same major/minor you target).
- The project installed with its dependencies, plus PyInstaller as a build-only
  dependency.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
pip install pyinstaller
```

### 2.2 Freeze-friendly codebase choices

Freezing exposes assumptions that are easy to miss in a source checkout. The
current structure addresses the important ones:

1. **Locating the dashboard file.**
   `app.py` computes
   `DASHBOARD_FILE = Path(__file__).resolve().parent / "assets" / "vampire-dashboard.html"`,
   resolving the dashboard as package data. The PyInstaller spec collects that
   package asset so the same package-relative path works in editable installs,
   wheels, and frozen bundles.

2. **The Uvicorn factory import string.**
   `vampire serve` and the desktop launcher import `create_app` directly and pass
   an application object to Uvicorn. That avoids relying on runtime import-string
   discovery inside the bundle.

3. **A GUI/desktop entry point (recommended, optional).**
   For a true "double-click" experience the exe should not require typing
   `vampire serve`. The `vampire-desktop` launcher starts the server and opens
   the browser to the dashboard while keeping the existing CLI intact.

> These are small, localized changes. Items 1 and 2 are correctness fixes for
> *any* frozen/packaged distribution; item 3 is UX polish for non-technical
> Windows users.

### 2.3 Hidden imports and data files

PyInstaller follows `import` statements statically, so anything imported
dynamically (by string) must be declared. For this stack expect to declare:

- **Uvicorn internals** that are selected at runtime by name, e.g.
  `uvicorn.lifespan.on`, `uvicorn.lifespan.off`,
  `uvicorn.loops.auto`, `uvicorn.protocols.http.auto`,
  `uvicorn.protocols.http.h11_impl`, `uvicorn.protocols.websockets.auto`.
- **Vampire submodules** that are only referenced via the factory import string
  (`vampire.app`, `vampire.api.control`, `vampire.api.openai_compat`, etc.).
  Using `--collect-submodules vampire` is the safe catch-all.
- **`zeroconf`** ships compiled Cython extensions and async helpers; use
  `--collect-all zeroconf` so its binary modules come along.
- **`pydantic` / `pydantic_core`** — Pydantic v2 has a compiled `pydantic_core`
  extension. Recent PyInstaller versions include hooks, but pin a current
  PyInstaller and verify; otherwise add `--collect-all pydantic`.
- **The `src/vampire/assets/vampire-dashboard.html` asset** must be added as data:
  `collect_data_files("vampire", includes=["assets/vampire-dashboard.html"])` in the committed spec file.

### 2.4 Build command (quick start)

A one-folder build is the most reliable starting point (faster startup, easiest
to debug):

```powershell
pyinstaller --name LLMVampire ^
  --console ^
  --collect-submodules vampire ^
  --collect-all zeroconf ^
  --collect-all pydantic ^
  --hidden-import uvicorn.lifespan.on ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --collect-data vampire ^
  --icon packaging\common\icons\LLMVampire.ico ^
  src\vampire\desktop\launcher.py
```

The result is `dist\LLMVampire\LLMVampire.exe` plus its support
folder. For a single self-contained file, swap to `--onefile` (see §2.6 for the
trade-off). Convert one of the existing PNG logos (`LOGO.png` / `LOGO-3.png`) to
a multi-resolution `.ico` for `--icon`.

### 2.5 A committed `.spec` file (recommended for repeatability)

Rather than a long command line, commit a PyInstaller **spec file** (e.g.
`packaging/windows/LLMVampire.spec`) that encodes the entry point, hidden
imports, `datas` (the package dashboard asset), icon, and one-file vs one-folder choice.
CI and contributors then build with a single `pyinstaller LLMVampire.spec`.
This keeps the build reproducible and reviewable.

### 2.6 One-file vs one-folder

| Mode | Pros | Cons |
| --- | --- | --- |
| `--onefile` | A single `.exe` to hand someone | Slower startup (unpacks to a temp dir each launch); harder AV behaviour; `sys._MEIPASS` path handling required |
| `--onedir` (default) | Fast startup, easy to inspect/patch, plays nicer with antivirus | Distributes a folder (ship as a `.zip` or wrap in an installer) |

For "send my friend one file," use `--onefile`. For a polished product install,
use `--onedir` wrapped in an installer (§4).

---

## 3. Building in CI (no Windows machine needed)

Because PyInstaller can't cross-compile, build the Windows artifact on a
`windows-latest` GitHub Actions runner. The outline of a release workflow:

1. `runs-on: windows-latest`.
2. `actions/setup-python` with the target Python version.
3. `pip install -e .` then `pip install pyinstaller`.
4. `pyinstaller packaging/windows/LLMVampire.spec`.
5. Smoke-test the artifact (see §6) — fail the build if the exe doesn't start.
6. Upload with `actions/upload-artifact`, and on tags attach the zipped build to
   a GitHub Release.

This gives reproducible, signed-on-CI binaries triggered by version tags, and
fits the existing CI conventions in [`.github/workflows`](../.github/workflows).

---

## 4. Turning the build into a real installer (optional but recommended)

A bare `.exe` (or zipped folder) works, but Windows users expect an installer.
Common choices that pair well with a PyInstaller `--onedir` build:

- **Inno Setup** — free, script-driven, produces a familiar `Setup.exe`; can add
  Start-menu shortcuts, a desktop icon, and an uninstaller.
- **WiX Toolset** — produces a `.msi` for managed/enterprise deployment.
- **NSIS** — lightweight scriptable installer.

The installer wraps the `dist\LLMVampire\` folder, creates shortcuts to
`LLMVampire.exe`, and registers an uninstaller. For Microsoft Store
distribution you would instead produce an **MSIX** package.

---

## 5. Code signing and antivirus

Unsigned executables — and PyInstaller one-file builds in particular — frequently
trigger SmartScreen warnings and false-positive antivirus detections.

- **Authenticode code signing** with an OV or EV certificate (via `signtool`)
  removes the "unknown publisher" warning and dramatically reduces false
  positives. EV certificates additionally build SmartScreen reputation
  immediately.
- Sign **both** the inner `.exe` and the installer.
- Prefer `--onedir` if AV false positives are a problem; it is flagged less often
  than `--onefile`.
- Building in clean CI (not a dev machine) reduces the chance of bundling
  something that trips heuristics.

Code signing requires purchasing a certificate from a trusted CA; budget for this
if the binary is for public distribution.

---

## 6. Testing the artifact

A frozen app can fail in ways the source tree never does (missing hidden import,
unbundled data file, subprocess spawn). Always smoke-test the built `.exe`:

1. Run it on a **clean** Windows machine/VM with **no Python installed** — this
   is the only honest test of self-containment.
2. Confirm the gateway starts and binds its port (default `7777`, see
   [`src/vampire/config.py`](../src/vampire/config.py)).
3. Hit `GET /vampire/v1/status` and an OpenAI-compatible route.
4. Open `/` and confirm the dashboard UI loads (verifies the
   `src/vampire/assets/vampire-dashboard.html` bundling from §2.2).
5. Verify graceful shutdown and that no orphaned processes remain.

Wire at least steps 2–4 into the CI job so a broken bundle fails the build.

---

## 7. Alternatives to PyInstaller

| Tool | When to choose it | Notes |
| --- | --- | --- |
| **Nuitka** | Want genuine compilation to C for speed and harder-to-reverse binaries | True compiler; produces fast standalone `.exe`; longer build times; still needs the data-file/hidden-import care from §2 |
| **cx_Freeze** | Prefer a `setup.py`-driven freeze | Mature; integrates with MSI via its `bdist_msi`; smaller community hook set than PyInstaller |
| **py2exe** | Legacy Windows-only freezing | Older, Windows-only, less active; generally superseded by PyInstaller |
| **Embeddable Python + launcher** | Maximum control, minimal magic | Ship the official Windows *embeddable* Python zip + a `.bat`/tiny `.exe` launcher + a vendored virtualenv; most manual, but no freezing surprises |
| **BeeWare Briefcase** | Want a native installer/app-store packaging story | More oriented to GUI apps; heavier framework buy-in |

For this project, **PyInstaller is the recommended default** and **Nuitka is the
strongest upgrade path** if compilation speed or binary hardening becomes a goal.

---

## 8. Summary checklist

To ship a distributable Windows `.exe`:

- [x] Move `vampire-dashboard.html` into `src/vampire/assets/` and resolve it as a package asset in `app.py`.
- [ ] Start Uvicorn from the imported `create_app` callable (no reload/workers
      subprocesses) for freeze-safety.
- [x] Add the `vampire-desktop` launcher entry point that starts the server and opens the dashboard.
- [x] Commit `packaging/windows/LLMVampire.spec` with hidden imports and bundled package data.
- [ ] Build on Windows (locally or `windows-latest` CI); never cross-compile.
- [ ] Smoke-test the `.exe` on a clean, Python-free Windows machine.
- [ ] (Recommended) Wrap in an installer (Inno Setup / WiX) and **code-sign**
      the binary and installer.
- [ ] Publish via GitHub Releases (and/or MSIX for the Microsoft Store).
