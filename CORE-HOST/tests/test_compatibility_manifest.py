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


def test_manifest_declares_server_and_legacy_client_platforms():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    server = data["server_deployment"]
    assert server["os"] == "linux"
    assert server["distribution"] == "void"
    assert server["architectures"] == ["x86_64"]
    assert server["libc"] == "glibc"
    assert server["init"] == "runit"

    entries = data["supported_operating_systems"]
    server_entries = [entry for entry in entries if entry["role"] == "server"]
    assert len(server_entries) == 1
    assert server_entries[0]["distribution"] == "void"
    assert server_entries[0]["architectures"] == ["x86_64"]

    legacy = {
        entry["os"]: set(entry["architectures"])
        for entry in entries
        if entry["role"] == "legacy-client"
    }
    assert legacy["windows"] == {"x86_64", "arm64"}
    assert legacy["macos"] == {"x86_64", "arm64"}
    assert legacy["linux"] == {"x86_64", "arm64"}


def test_manifest_declares_rescs_and_release_artifact_naming():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["components"]["rescs"]["version"] == "0.4.0"
    assert data["server_deployment"]["install_methods"] == ["source-release-archive"]
    assert data["build_metadata"]["artifact_naming"] == (
        "CORE-Server-{version}-void-x86_64-{format}"
    )
