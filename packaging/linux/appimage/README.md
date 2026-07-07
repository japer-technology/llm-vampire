# AppImage

AppImage build recipes and metadata for a single-file, self-contained Linux
distributable of LM Studio Vampire will live here.

> Status: **planned**. No AppImage recipe is finalized yet; this folder is a
> placeholder that documents the intended approach.

## Goal

Produce a portable `LM Studio Vampire-<version>-x86_64.AppImage` that runs on
most modern Linux distributions without installation, wrapping the same
`vampire-desktop` launcher (`vampire.desktop.launcher:main`) that the other
packaging targets use.

## Intended approach

1. Build the application (a PyInstaller onedir bundle or the installed wheel with
   its Python runtime) into an `AppDir` tree.
2. Add AppImage metadata to the `AppDir`:
   - a `.desktop` entry (mirror
     [`../../ubuntu/lmstudio-vampire.desktop`](../../ubuntu/lmstudio-vampire.desktop)),
   - an application icon from [`../../common/icons/`](../../common/icons/),
   - an `AppRun` entry point that starts `vampire-desktop`.
3. Package the `AppDir` with `appimagetool` to emit the `.AppImage`.

## When implemented

Add a `scripts/packaging/build-linux-appimage.sh` helper and reference it here,
then verify the output against [`../../common/smoke-test.md`](../../common/smoke-test.md).
