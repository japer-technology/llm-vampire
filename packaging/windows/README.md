# Windows packaging

Build the native Windows executable on Windows. PyInstaller is not a cross-compiler.

```powershell
.\scripts\packaging\build-windows.ps1
```

The PyInstaller spec targets `vampire.desktop.launcher` so the packaged app starts
the gateway and opens the bundled dashboard.
