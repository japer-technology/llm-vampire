# Contributing to `lmstudio-vampire`

Thank you for your interest in improving **LM Studio Vampire**. This project turns
owner-approved LM Studio endpoints into one governed, private AI service. The
canonical reference implementation is the Python package under
[`src/vampire/`](src/vampire/) (see [METHOD-A.md](METHOD-A.md)); every install
pathway, OS application, and SDK hangs off that single source of truth.

## Code of Conduct

This project is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By
participating you are expected to uphold it. Please report unacceptable behaviour
as described there.

## Ways to contribute

- **Report bugs** and **request features** using the
  [issue templates](.github/ISSUE_TEMPLATE/).
- **Improve documentation** in [`docs/`](docs/) — the user manual, install
  pathways, packaging recipes, and SDK guides.
- **Add or harden install pathways** under [`packaging/`](packaging/) and OS
  applications under [`apps/`](apps/).
- **Build SDKs** under [`sdks/`](sdks/).
- **Fix or extend the Python core** under [`src/vampire/`](src/vampire/).

## Development setup

The project targets **Python 3.10+**.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

This installs the package, the `vampire` console script, and the development
tools (`ruff`, `mypy`, `pytest`).

## Validation — run before every PR

The same checks CI runs must pass locally from the repository root:

```bash
ruff format --check .
ruff check .
mypy
pytest
```

All four must pass on a clean checkout. Run `ruff format .` to auto-fix
formatting.

## Pull request process

1. Fork and create a topic branch. Branch names are prefixed with your GitHub
   username (for example `yourname/short-description`).
2. Keep changes **additive and reversible** — preserve the stable public surface:
   the project name `lmstudio-vampire`, the CLI command `vampire`, and the default
   port `7777`.
3. Add or update tests. Each implementation phase has a dedicated
   `tests/test_phaseN.py` suite; cross-cutting behaviour lives in
   `tests/test_cli.py` and `tests/test_smoke.py`.
4. Update relevant documentation under [`docs/`](docs/).
5. Ensure the full validation suite passes.
6. Open a PR using the [pull request template](.github/PULL_REQUEST_TEMPLATE.md)
   and link any related issues.

## Commit and versioning conventions

- Write clear, imperative commit subjects (for example `Add Homebrew formula`).
- The project follows [Semantic Versioning](https://semver.org/). User-facing
  changes are recorded in [CHANGELOG.md](CHANGELOG.md) under the `Unreleased`
  heading.

## Project layout

See the [repository layout](docs/README.md) for where each kind of contribution
belongs. In short:

| Area | Location |
| --- | --- |
| Python reference implementation | `src/vampire/` |
| Tests | `tests/` |
| Install / distribution recipes | `packaging/` |
| OS application shells | `apps/` |
| Client SDKs | `sdks/` |
| Repository tooling | `tools/` |
| Documentation | `docs/` |
| Brand assets | `branding/` |

## License

By contributing, you agree that your contributions are licensed under the same
terms as the project (see [LICENSE.md](LICENSE.md)).
