# Linux packaging

`LMStudioVampire.spec` produces the standalone application directory used by
both Linux release formats:

```bash
scripts/packaging/build-linux.sh
scripts/packaging/build-ubuntu-deb.sh
```

The automated target is x86-64. AppImage is not supported. Use `uv build`
separately for Python wheels and source distributions. See
[`../../BUILDING.md`](../../BUILDING.md).
