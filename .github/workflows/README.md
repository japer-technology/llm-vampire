# GitHub Actions workflows

`ci.yml` runs Ruff formatting and lint checks, strict mypy, and pytest on Python
3.10, 3.11, and 3.12.

`packaging.yml` runs manually or for `v*.*.*` tags. It uses locked Python
dependencies and native x86-64 runners to produce:

- Linux standalone archive and Debian package
- macOS application ZIP
- Windows portable ZIP and installer

Manual runs validate and upload workflow artifacts without publishing. Tag runs
add a final least-privilege job with `contents: write`; that job checks all files,
generates `SHA256SUMS.txt`, and creates exactly one release containing separate
assets. See [`../../BUILDING.md`](../../BUILDING.md).
