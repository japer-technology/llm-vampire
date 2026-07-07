# Common packaging assets

Cross-platform packaging material that is shared by every target lives here so it
is authored once and reused by the Linux, macOS, Ubuntu, and Windows builds.

## Contents

| Path | Purpose |
| --- | --- |
| [`smoke-test.md`](smoke-test.md) | Manual acceptance checklist to run against every packaged artifact on a clean machine before release. |
| [`icons/`](icons/) | Generated platform icon files consumed by the packaging specs (`.ico` for Windows, `.icns` for macOS, `.png` for Linux/Ubuntu). |
| [`release-metadata/`](release-metadata/) | Shared release notes, signing metadata, and platform store metadata templates. |

## When to add something here

Put an asset in `common/` when it is genuinely platform-neutral or when the same
source is transformed into per-platform variants (for example, one master logo
exported to `.ico`, `.icns`, and multiple `.png` sizes). Platform-specific build
recipes belong in the matching `linux/`, `macos/`, `ubuntu/`, or `windows/`
folder instead.

## Smoke test

`smoke-test.md` is the release gate for packaged builds: it verifies the app
binds the configured gateway port (default `7777`), serves the bundled dashboard
at `http://127.0.0.1:7777/`, answers `GET /vampire/v1/status`, and exits cleanly.
Run it for each platform artifact you intend to publish.
