# GitHub Actions workflows

Automation for `lmstudio-vampire`. Every workflow installs the package with
`pip install -e ".[dev]"` and runs the same quality gates used locally:
`ruff format --check .`, `ruff check .`, `mypy`, and `pytest`.

## Workflows

| Workflow | File | Triggers | Purpose |
| --- | --- | --- | --- |
| CI | [`ci.yml`](ci.yml) | Pull requests; pushes to `main` | Lint, format-check, type-check, and test on Python 3.10, 3.11, and 3.12 |
| Packaging | [`packaging.yml`](packaging.yml) | Manual dispatch; `v*` tags; published releases | Build and upload distributable artifacts |

## CI (`ci.yml`)

A single `test` job runs on `ubuntu-latest` across a Python version matrix
(3.10 / 3.11 / 3.12, `fail-fast: false`). All four gates must pass:

1. `python -m ruff format --check .`
2. `python -m ruff check .`
3. `python -m mypy`
4. `python -m pytest`

Run the same commands locally from the repository root before pushing to keep
CI green.

## Packaging (`packaging.yml`)

Runs a `validate` job (same four gates on Python 3.12), then builds per-platform
artifacts with the scripts in [`scripts/packaging/`](../../scripts/packaging/README.md):

| Job | Runner | Script(s) | Artifact |
| --- | --- | --- | --- |
| `linux-source` | `ubuntu-latest` | `build-linux-source.sh`, `build-html-apps.sh` | `linux-source-and-html` (wheel, sdist, HTML helper apps) |
| `macos-app` | `macos-latest` | `build-macos.sh` | `macos-app` (`LM Studio Vampire.app`) |
| `windows-folder` | `windows-latest` | `build-windows.ps1` | `windows-folder` (`LMStudioVampire/`) |
| `attach-to-release` | `ubuntu-latest` | — | Zips the artifacts, generates `SHA256SUMS.txt`, and uploads everything to the GitHub release (release events only) |

## Conventions

- Workflows request the minimum permissions they need (`contents: read` by
  default; `attach-to-release` elevates to `contents: write`).
- Keep the validation steps in `ci.yml` and `packaging.yml` in sync with the
  tooling configured in [`pyproject.toml`](../../pyproject.toml).
