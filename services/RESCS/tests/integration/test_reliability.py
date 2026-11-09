"""Integration: reliability, dependency failure, clean-install smoke.

Covers §17 (installation sanity), §23 (controlled dependency failure),
and §32 (bounded endurance — short by design, never a 24h pytest).
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rescs import __version__
from rescs.config import Settings
from rescs.db.bootstrap import bootstrap_database
from rescs.errors import RESCSError
from rescs.main import create_app

RECORDS = "/api/v1/records"
FILES = "/api/v1/files"


def test_package_version_matches_project_metadata():
    import tomllib

    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    declared = tomllib.loads(pyproject.read_text())["project"]["version"]
    assert __version__ == declared


def test_declared_dependencies_agree():
    root = Path(__file__).resolve().parents[2]
    requirements = (root / "requirements.txt").read_text()
    dev_requirements = (root / "requirements-dev.txt").read_text()
    assert "-r requirements.txt" in dev_requirements
    for package in ("fastapi==", "sqlalchemy==", "pydantic==", "pydantic-settings=="):
        assert package in requirements, f"{package} missing from requirements.txt"
    assert "pytest==" in dev_requirements
    assert "httpx==" in dev_requirements
    # The runtime surface the app actually needs imports cleanly.
    import fastapi  # noqa: F401


def test_application_factory_boots_independently(settings: Settings):
    app = create_app(settings=settings)
    with TestClient(app, headers={"X-API-Key": settings.api_key}) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 200
        assert client.get("/api/v1/contract").status_code == 200


def test_no_cross_subsystem_imports():
    root = Path(__file__).resolve().parents[2] / "src" / "rescs"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text()
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                for foreign in ("core.", "core ", "asis", "tiviss", "ascs", "radarsard"):
                    if foreign in stripped and "rescs" not in stripped:
                        offenders.append(f"{path.name}: {stripped}")
    assert offenders == []


def test_unreachable_database_fails_fast_with_domain_error(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        api_key="test-api-key-0123456789abcdef",
        database_url=f"sqlite:///{tmp_path}/no-such-dir-xyz/rescs.db",
        environment="test",
    )
    with pytest.raises(RESCSError) as exc_info:
        bootstrap_database(settings)
    assert exc_info.value.code in ("DEPENDENCY_UNAVAILABLE", "STORAGE_ERROR")
    # No credentials exist here to leak, but the envelope shape must hold.
    assert exc_info.value.to_dict()["code"]


def test_readiness_reflects_storage_outage_on_persistent_app(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        api_key="test-api-key-0123456789abcdef",
        database_url=f"sqlite:///{tmp_path}/rescs.db",
        storage_dir=str(tmp_path / "blobs"),
        environment="test",
    )
    with TestClient(
        create_app(settings=settings), headers={"X-API-Key": settings.api_key}
    ) as client:
        assert client.get("/health/ready").status_code == 200
        client.app.state.health.register("storage", lambda: "down")
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {
            "status": "not_ready",
            "checks": {"database": "ok", "storage": "down"},
        }


def test_bounded_endurance_no_corruption(client: TestClient):
    """Short reliability loop: repeated ops stay healthy and consistent."""
    budget = float(os.environ.get("RESCS_ENDURANCE_SECONDS", "5"))
    deadline = time.perf_counter() + budget
    operations = 0
    created_id: str | None = None
    while time.perf_counter() < deadline:
        staged = client.post(
            RECORDS,
            json={"namespace": "endurance", "key": f"k-{operations}", "value": {"n": operations}},
            headers={"X-Request-ID": f"endurance-{operations}"},
        )
        assert staged.status_code == 201
        assert staged.headers.get("X-Request-ID") == f"endurance-{operations}"
        if created_id is None:
            created_id = staged.json()["id"]
        assert client.get(f"{RECORDS}/{created_id}").status_code == 200
        assert client.get(f"{RECORDS}?namespace=endurance&limit=10").status_code == 200
        blob = client.post(
            FILES, files={"upload": (f"e-{operations}.bin", b"e" * 64, "application/octet-stream")}
        )
        assert blob.status_code == 201
        assert client.get("/health/ready").status_code == 200
        operations += 1
    assert operations >= 1, "endurance loop made no progress"
    # State left behind is still coherent.
    assert client.get(f"{RECORDS}/{created_id}").status_code == 200
    assert client.get("/health/ready").json()["status"] == "ready"

