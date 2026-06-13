"""Allow ``python -m vampire`` to invoke the CLI."""

from vampire.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
