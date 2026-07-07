# Ubuntu packaging

Debian/Ubuntu `.deb` package metadata and desktop integration for LM Studio
Vampire. The resulting package installs the `vampire` CLI, the `vampire-desktop`
launcher, and a desktop entry so the app appears in the applications menu.

## Build

```bash
scripts/packaging/build-ubuntu-deb.sh
```

> Status: the script currently builds the wheel and sdist (`python -m build`) and
> prints where the Debian metadata lives. The full `dpkg-buildpackage` recipe is
> a work in progress — install `debhelper`/`dpkg-dev` and extend the script to
> produce the final `.deb`.

## Files in this folder

| File | Purpose |
| --- | --- |
| [`debian/`](debian/) | Debian source-package control files (see its README). |
| [`lmstudio-vampire.desktop`](lmstudio-vampire.desktop) | Desktop entry that runs `vampire-desktop` (no terminal), categorized under Development/Network. |

## Desktop entry

`lmstudio-vampire.desktop` launches the gateway and dashboard via
`Exec=vampire-desktop`. When wiring an icon, add an `Icon=` line pointing at an
installed PNG from [`../common/icons/`](../common/icons/) and install the icon to
the standard hicolor theme paths.

## Runtime configuration

The gateway defaults to `127.0.0.1:7777` proxying `http://localhost:1234`.
Override with `VAMPIRE_HOST`, `VAMPIRE_PORT`, `VAMPIRE_LMSTUDIO_BASE_URL`,
`VAMPIRE_LOG_LEVEL`, or `VAMPIRE_AUTH_TOKEN` (via environment or a `.env` file).

## Verify

Install the built package on a clean Ubuntu VM and run
[`../common/smoke-test.md`](../common/smoke-test.md) before publishing.
