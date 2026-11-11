"""Frozen-executable entry point for CORE-HOST (used only by PyInstaller)."""

from core.entrypoint import main

if __name__ == "__main__":
    raise SystemExit(main())
