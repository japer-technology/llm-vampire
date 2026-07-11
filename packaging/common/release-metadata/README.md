# Release metadata

Release version validation and artifact checksum generation live in
`scripts/packaging/version.py` and `scripts/packaging/validate-artifacts.py`.
Native installer metadata receives the validated version at build time.

See [`../../../BUILDING.md`](../../../BUILDING.md) for the release process and
reserved signing secret names.
