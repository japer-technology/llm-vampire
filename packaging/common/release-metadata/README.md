# Release metadata

Shared, non-binary release material that is authored once and reused across every
platform build lives here.

## Intended contents

- **Release notes** — the canonical changelog / "what's new" text for a version,
  which per-platform stores and installers can quote from.
- **Signing metadata templates** — non-secret templates and instructions for
  code-signing and notarization (macOS notarization profiles, Windows
  Authenticode subject details). Never commit private keys, certificates, App
  Store Connect credentials, or signing passwords here — keep those in the CI
  secret store.
- **Store / distribution metadata** — descriptions, categories, and other
  listing fields reused across distribution channels.

## Versioning

Keep version strings consistent with the source of truth in
[`pyproject.toml`](../../../pyproject.toml) (currently `0.0.1`) and the
per-platform specs that hard-code it (`packaging/macos/Info.plist`,
`packaging/windows/installer.iss`). Update all of them together when cutting a
release.
