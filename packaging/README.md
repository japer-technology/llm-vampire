# Packaging

This directory contains native packaging definitions for the
`vampire.desktop.launcher:main` application entry point.

| Path | Purpose |
| --- | --- |
| `linux/LMStudioVampire.spec` | Linux standalone PyInstaller directory |
| `ubuntu/lmstudio-vampire.desktop` | Debian/Ubuntu desktop integration |
| `macos/LMStudioVampire.spec` | macOS `.app` bundle |
| `macos/entitlements.plist` | macOS runtime entitlements |
| `windows/LMStudioVampire.spec` | Windows portable application directory |
| `windows/installer.iss` | Inno Setup installer |
| `html/` | Optional standalone HTML helper tools |
| `common/smoke-test.md` | Manual post-package smoke test |

The previous Debian metadata was incomplete, the AppImage directory was only a
placeholder, and the workflow wrapped unrelated platform outputs in generic
ZIPs. Those obsolete paths have been replaced by native, versioned artifacts.

See [`../BUILDING.md`](../BUILDING.md) for prerequisites, exact commands,
supported targets, release instructions, and signing limitations.
