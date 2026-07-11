# Debian/Ubuntu packaging

The package installs the standalone `vampire-desktop` executable and the desktop
menu entry in `lmstudio-vampire.desktop`. Build it on Debian or Ubuntu:

```bash
scripts/packaging/build-ubuntu-deb.sh
```

The script creates control metadata from the validated release version and uses
`dpkg-deb` to produce the final package. It builds the Linux executable first
when needed. See [`../../BUILDING.md`](../../BUILDING.md).
