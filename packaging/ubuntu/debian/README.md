# Debian control files

Source-package metadata consumed by Debian tooling (`dpkg-buildpackage`,
`debhelper`) when producing the `lmstudio-vampire` `.deb`.

## Files

| File | Purpose |
| --- | --- |
| [`control`](control) | Declares the source and binary package: section `net`, `debhelper-compat (= 13)` and Python build deps, an `all`-architecture binary depending on `python3`, and the package description. |

## Expected additions

A complete Debian source package typically also needs the following alongside
`control` (add them as the `.deb` recipe is finalized):

- `changelog` — Debian-format version history driving the package version.
- `rules` — the `debhelper`-based build script (executable, `#!/usr/bin/make -f`).
- `copyright` — machine-readable license (the project is MIT; see
  [`../../../LICENSE.md`](../../../LICENSE.md)).
- `install` / `*.desktop` wiring so
  [`../lmstudio-vampire.desktop`](../lmstudio-vampire.desktop), the `vampire`
  CLI, and the `vampire-desktop` launcher land in the right locations.

## Consistency

Keep the package version aligned with [`pyproject.toml`](../../../pyproject.toml)
(currently `0.0.1`) and the `Maintainer:` field in step with the project owner
(`japer-technology`).

## Building

Invoke the packaging build from the repository root, not from this folder:

```bash
scripts/packaging/build-ubuntu-deb.sh
```
