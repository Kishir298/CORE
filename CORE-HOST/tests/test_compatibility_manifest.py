"""The compatibility manifest must match the shipped protocol contract."""

from __future__ import annotations

import json
from pathlib import Path

from core.communication.protocol import SUPPORTED_PROTOCOL_VERSION
from core.version import __version__

MANIFEST = Path(__file__).resolve().parents[2] / "compatibility.json"


def test_manifest_matches_package_and_protocol():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["project"] == "CORE"
    assert data["version"] == __version__
    assert data["components"]["host"]["version"] == __version__
    assert data["components"]["client"]["version"] == __version__
    assert data["core_protocol"]["version"] == SUPPORTED_PROTOCOL_VERSION
    assert SUPPORTED_PROTOCOL_VERSION in data["core_protocol"]["supported_versions"]


def test_manifest_declares_all_required_platforms():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    systems = {entry["os"]: set(entry["architectures"]) for entry in data["supported_operating_systems"]}
    assert systems["windows"] >= {"x86_64", "arm64"}
    assert systems["macos"] == {"x86_64", "arm64"}
    assert systems["linux"] >= {"x86_64"}
