# Packaging scripts

Run these scripts from the repository root after:

```bash
uv sync --frozen --extra packaging
```

| Script | Host | Output |
| --- | --- | --- |
| `build-linux.sh` | Linux | standalone `.tar.gz` |
| `build-ubuntu-deb.sh` | Debian/Ubuntu | native `.deb` |
| `build-macos.sh` | macOS | ZIP containing the `.app` |
| `build-windows.ps1` | Windows | portable ZIP and Inno Setup installer |
| `build-html-apps.sh` | Bash | optional HTML helper files |
| `version.py` | Any | validates metadata and an optional release tag |
| `validate-artifacts.py` | Any | validates outputs and checksums |

The native package scripts resolve the project version, honor `RELEASE_TAG` when
set, and fail on metadata mismatches or missing outputs. Full instructions are
in [`../../BUILDING.md`](../../BUILDING.md).
