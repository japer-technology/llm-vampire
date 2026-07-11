# macOS packaging

Build the native application ZIP on macOS:

```bash
scripts/packaging/build-macos.sh
```

`LMStudioVampire.spec` targets the desktop launcher, bundles the dashboard, and
injects the validated release version. `entitlements.plist` permits the local
server and outbound LM Studio connections.

The automated package is currently unsigned and not notarized. See
[`../../BUILDING.md`](../../BUILDING.md) for prerequisites, supported
architecture, reserved signing secret names, and release instructions.
