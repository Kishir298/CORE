"""Void Linux first-run configuration must keep CORE and RESCS keys aligned."""
from __future__ import annotations

import importlib.util
import json
import os
import stat
from pathlib import Path

import pytest

CONFIGURE_PATH = Path(__file__).resolve().parents[2] / "deployment" / "void" / "configure.py"


def load_configure():
    spec = importlib.util.spec_from_file_location("void_configure", CONFIGURE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def env_value(path: Path, name: str) -> str:
    for line in path.read_text().splitlines():
        key, _, value = line.partition("=")
        if key == name:
            return value
    return ""


def test_first_run_writes_one_key_to_rescs_and_both_gateways(tmp_path):
    configure = load_configure()
    base, data = tmp_path / "etc", tmp_path / "data"

    configure.configure(base, data, "https://core.example.test")

    key = env_value(base / "rescs.env", "RESCS_API_KEY")
    canonical = json.loads((base / "gateway.json").read_text())
    loaded = json.loads((data / "core" / "gateway.json").read_text())
    assert key
    assert canonical["rescs_key"] == loaded["rescs_key"] == key
    assert canonical["public_origin"] == loaded["public_origin"] == "https://core.example.test"
    assert canonical["rescs_url"] == loaded["rescs_url"] == "http://127.0.0.1:8081"
    assert (base / "gateway.json").read_bytes() == (data / "core" / "gateway.json").read_bytes()
    if os.name != "nt":
        assert stat.S_IMODE((data / "core" / "gateway.json").stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "relative",
    ["etc/core.env", "etc/rescs.env", "etc/gateway.json", "data/core/gateway.json"],
)
def test_existing_configuration_is_never_overwritten(tmp_path, relative):
    configure = load_configure()
    base, data = tmp_path / "etc", tmp_path / "data"
    existing = tmp_path / relative
    existing.parent.mkdir(parents=True)
    existing.write_text("sentinel\n")
    before = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}

    with pytest.raises(SystemExit):
        configure.configure(base, data, "https://core.example.test")

    assert existing.read_text() == "sentinel\n"
    assert {path.relative_to(tmp_path) for path in tmp_path.rglob("*")} == before


def test_second_run_does_not_rotate_keys(tmp_path):
    configure = load_configure()
    base, data = tmp_path / "etc", tmp_path / "data"
    configure.configure(base, data, "https://core.example.test")
    paths = [
        base / "core.env",
        base / "rescs.env",
        base / "gateway.json",
        data / "core" / "gateway.json",
    ]
    before = {path: path.read_bytes() for path in paths}

    with pytest.raises(SystemExit):
        configure.configure(base, data, "https://changed.example.test")

    assert {path: path.read_bytes() for path in paths} == before


def test_reconcile_adopts_canonical_gateway_without_rotating_key(tmp_path):
    configure = load_configure()
    base, data = tmp_path / "etc", tmp_path / "data"
    configure.configure(base, data, "https://core.example.test")
    canonical = (base / "gateway.json").read_text()
    loaded = data / "core" / "gateway.json"
    loaded.unlink()

    configure.reconcile(base, data)

    assert loaded.read_text() == canonical
    assert json.loads(canonical)["rescs_key"] == env_value(base / "rescs.env", "RESCS_API_KEY")


@pytest.mark.parametrize("target", ["canonical", "loaded"])
def test_reconcile_refuses_an_existing_mismatched_key(tmp_path, target):
    configure = load_configure()
    base, data = tmp_path / "etc", tmp_path / "data"
    configure.configure(base, data, "https://core.example.test")
    path = base / "gateway.json" if target == "canonical" else data / "core" / "gateway.json"
    path.write_text(json.dumps({"rescs_key": "different-key"}))

    with pytest.raises(SystemExit):
        configure.reconcile(base, data)

    assert json.loads(path.read_text())["rescs_key"] == "different-key"
