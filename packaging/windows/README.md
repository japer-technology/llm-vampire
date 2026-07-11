# Windows packaging

Build both Windows x86-64 release files from PowerShell:

```powershell
.\scripts\packaging\build-windows.ps1
```

`LMStudioVampire.spec` produces the windowed portable application and
`installer.iss` wraps it in an Inno Setup installer. The validated release
version is passed to Inno Setup rather than stored in either definition.

The packages are currently unsigned. See
[`../../BUILDING.md`](../../BUILDING.md) for prerequisites, output names,
reserved signing secret names, and release instructions.
