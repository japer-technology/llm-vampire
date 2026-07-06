# Build from source on Linux

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
python -m pytest
python -m build
```

The source build remains the recompilable Linux path. Platform-specific
distributables can wrap the same Python package and `vampire-desktop` launcher.
