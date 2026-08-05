# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

spec_dir = Path(SPECPATH)
repo_root = spec_dir.parents[1]
release_version = os.environ["RELEASE_VERSION"]

datas = collect_data_files("vampire", includes=["assets/vampire-dashboard.html"])
hiddenimports = collect_submodules("vampire")

a = Analysis(
    [str(repo_root / "src/vampire/desktop/launcher.py")],
    pathex=[str(repo_root)],
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
    name="LLMVampire",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
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
    upx=False,
    upx_exclude=[],
    name="LLMVampire",
)

app = BUNDLE(
    coll,
    name="LLM Vampire.app",
    icon=None,
    bundle_identifier="technology.japer.llm-vampire",
    info_plist={
        "CFBundleDisplayName": "LLM Vampire",
        "CFBundleShortVersionString": release_version,
        "CFBundleVersion": release_version,
        "LSMinimumSystemVersion": "12.0",
    },
)
