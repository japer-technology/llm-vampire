# Icons

Generated, release-ready icon files for the packaged app live here. Icons are not
tracked as build inputs elsewhere: the packaging specs reference the files placed
in this folder.

## Required formats

| Platform | Format | Notes |
| --- | --- | --- |
| Windows | `.ico` | Multi-resolution `.ico` (16, 32, 48, 256 px) referenced by the PyInstaller spec / Inno Setup installer. |
| macOS | `.icns` | Apple icon set referenced by `packaging/macos/LMStudioVampire.spec` (currently `icon=None`; wire the `.icns` here when finalized). |
| Linux / Ubuntu | `.png` | The PNG sizes required by the target package and desktop entry (commonly 48, 64, 128, 256 px). |

## Source

Export every format from a single high-resolution master (the repository logo,
e.g. `LOGO-4.png` at the repo root) so all platforms stay visually consistent.
Regenerate all formats whenever the master artwork changes.

## Wiring icons into builds

- **macOS** — set `icon="../common/icons/<name>.icns"` in the `BUNDLE(...)` call
  of `packaging/macos/LMStudioVampire.spec`.
- **Windows** — set `icon="..\\common\\icons\\<name>.ico"` in the `EXE(...)` call
  of `packaging/windows/LMStudioVampire.spec`, and/or reference it from
  `packaging/windows/installer.iss`.
- **Ubuntu** — install the `.png` sizes and point `Icon=` in
  `packaging/ubuntu/lmstudio-vampire.desktop` at the installed icon name.
