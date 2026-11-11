"""Frozen-executable entry point for CORE-CLIENT (used only by PyInstaller)."""

from client.entrypoint import main

if __name__ == "__main__":
    raise SystemExit(main())
