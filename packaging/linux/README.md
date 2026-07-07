# Linux packaging

Generic Linux distribution artifacts that are **not** Ubuntu/Debian specific live
here — source rebuilds, wheels, sdists, and AppImage metadata. Debian/Ubuntu
`.deb` packaging lives in [`../ubuntu/`](../ubuntu/) instead.

## Build from source (recommended baseline)

The source build is the portable, recompilable Linux path. It produces a wheel
and sdist that wrap the same `vampire` CLI and `vampire-desktop` launcher.

```bash
scripts/packaging/build-linux-source.sh
```

The script upgrades `pip`, installs the package with dev extras plus `build`,
runs the test suite, and then runs `python -m build`. Artifacts land in `dist/`.
See [`build-from-source.md`](build-from-source.md) for the manual, step-by-step
equivalent using a virtual environment.

## Installing the result

```bash
pip install dist/lmstudio_vampire-<version>-py3-none-any.whl
vampire --help          # CLI
vampire-desktop         # launch gateway + dashboard
```

## Other Linux formats

| Format | Location | Status |
| --- | --- | --- |
| Wheel / sdist | `dist/` (via the script above) | Supported |
| AppImage | [`appimage/`](appimage/) | Planned — recipe placeholder |
| `.deb` | [`../ubuntu/`](../ubuntu/) | Metadata present, recipe WIP |

## Runtime notes

The gateway defaults to binding `127.0.0.1:7777` and proxying to an LM Studio
node at `http://localhost:1234`. Override with `VAMPIRE_HOST`, `VAMPIRE_PORT`,
and `VAMPIRE_LMSTUDIO_BASE_URL` (or a `.env` file) as needed. Validate any
artifact with [`../common/smoke-test.md`](../common/smoke-test.md).
