# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

spec_dir = Path(SPECPATH)

datas = collect_data_files("vampire", includes=["assets/vampire-dashboard.html"])
hiddenimports = collect_submodules("vampire")

a = Analysis(
    ["../../src/vampire/desktop/launcher.py"],
    pathex=["../.."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LMStudioVampire",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=str(spec_dir / "entitlements.plist"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="LMStudioVampire",
)

app = BUNDLE(
    coll,
    name="LM Studio Vampire.app",
    icon=None,
    bundle_identifier="technology.japer.lmstudio-vampire",
    info_plist=str(spec_dir / "Info.plist"),
)
