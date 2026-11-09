"""Support ``python -m tiviss`` as an alias for the ``tiviss`` console script."""

from tiviss.cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
