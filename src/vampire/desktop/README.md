# `vampire.desktop` — desktop launcher

Double-click friendly launcher used by packaged LLM Vampire desktop builds
(macOS `.app` bundle and Windows executable folder).

| Module | Purpose |
| --- | --- |
| [`launcher.py`](launcher.py) | Starts the gateway in-process and opens the browser dashboard, so a packaged build works without a terminal. Exposed as the `vampire-desktop` console script (`vampire.desktop.launcher:main` in [`pyproject.toml`](../../../pyproject.toml)) |

The launcher is the entry point that the PyInstaller-based packaging scripts in
[`scripts/packaging/`](../../../scripts/packaging/README.md) bundle into
platform artifacts. For terminal usage, prefer the primary `vampire` CLI
([`vampire/cli.py`](../cli.py)).
