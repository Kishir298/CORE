"""Support ``python -m asis`` as an alias for the ``asis`` console script."""

from asis.cli.main import entry

if __name__ == "__main__":
    raise SystemExit(entry())
