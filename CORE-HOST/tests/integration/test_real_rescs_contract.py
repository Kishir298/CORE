"""Contract test against the real R.E.S.C.S. FastAPI application.

Skipped unless the sibling R.E.S.C.S. checkout and its virtualenv are
available. No R.E.S.C.S. files are modified; it runs as a temporary
loopback subprocess with throwaway SQLite storage.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

from core.data.rescs_reader import HttpDataReader
from core.rescs.adapter import HttpRescsAdapter
from core.resources.models import Resource
from core.runtime.history import RuntimeRecord

API_KEY = "core-real-contract-key-0123456789"


def _paths() -> tuple[Path, Path]:
    root = Path(__file__).resolve().parents[4]
    source = Path(os.environ.get("CORE_TEST_RESCS_SOURCE", root / "RESCS"))
    python = Path(os.environ.get("CORE_TEST_RESCS_PYTHON", source / ".venv/bin/python"))
    return source, python


@pytest.fixture()
def real_rescs(tmp_path):
    source, python = _paths()
    if not (source / "src/rescs/main.py").is_file():
        pytest.skip("Sibling R.E.S.C.S. source is not available.")
    if not python.is_file():
        pytest.skip("Set CORE_TEST_RESCS_PYTHON to the real R.E.S.C.S. interpreter.")

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {
        **os.environ,
        "PYTHONPATH": str(source / "src"),
        "RESCS_API_KEY": API_KEY,
        "RESCS_ENV": "test",
        "RESCS_DATABASE_URL": "sqlite:///" + str(tmp_path / "rescs.sqlite3"),
        "RESCS_STORAGE_DIR": str(tmp_path / "objects"),
    }
    process = subprocess.Popen(
        [
            str(python),
            "-m",
            "uvicorn",
            "rescs.main:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            if process.poll() is not None:
                pytest.fail("Real R.E.S.C.S. exited during startup.")
            try:
                with urllib.request.urlopen(url + "/health/ready", timeout=0.2) as resp:
                    if resp.status == 200:
                        break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("Real R.E.S.C.S. did not become ready.")
        yield url
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _upload(url: str, content: bytes) -> dict:
    boundary = "core-real-contract-boundary"
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="owner"\r\n\r\n'
        f"system\r\n"
        f'--{boundary}\r\nContent-Disposition: form-data; name="upload"; '
        f'filename="real.bin"\r\nContent-Type: application/octet-stream\r\n\r\n'
    ).encode()
    body = head + content + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(
        url + "/api/v1/files",
        data=body,
        method="POST",
        headers={
            "X-API-Key": API_KEY,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def test_real_rescs_adapter_and_reader(real_rescs):
    adapter = HttpRescsAdapter(
        endpoint=real_rescs, timeout=5.0, fallback=False, api_key=API_KEY
    )
    health = adapter.health()
    assert health["healthy"] is True
    assert health["status"] == "ok"

    for index in range(501):
        adapter.persist_resource(
            Resource(
                resource_id=f"r{index:03d}",
                name=f"Resource {index}",
                resource_type="sensor",
                owner="alice",
            )
        )
    assert len(adapter.list_resources()) == 501

    adapter.persist_runtime(
        RuntimeRecord(entity_id="agent-real", entity_type="agent")
    )
    assert [record.entity_id for record in adapter.list_runtimes()] == ["agent-real"]

    adapter.persist_device({"device_id": "device-real", "name": "Real Device"})
    assert adapter.fetch_device("device-real")["name"] == "Real Device"

    reader = HttpDataReader(
        endpoint=real_rescs, owner_scope=None, allow_cross_owner=True, api_key=API_KEY
    )
    assert len(reader.list_records("core.resources")) == 501
    tail = reader.list_records("core.resources", limit=10, offset=491)
    assert len(tail) == 10
    assert reader.get_record("core.resources", "r500")["value"]["resource_id"] == "r500"
    found = reader.search_records("Resource 250", "core.resources")
    assert [record["key"] for record in found] == ["r250"]

    content = b"real-rescs-binary-content"
    meta = _upload(real_rescs, content)
    reader_files = HttpDataReader(
        endpoint=real_rescs,
        owner_scope="system",
        allow_cross_owner=True,
        api_key=API_KEY,
    )
    assert reader_files.get_file_metadata(meta["id"])["owner"] == "system"
    returned_meta, downloaded = reader_files.get_file_bytes(meta["id"])
    assert returned_meta["id"] == meta["id"]
    assert downloaded == content

    adapter.clear()
    assert reader.list_records("core.resources") == []
    assert reader.list_records("core.runtimes") == []
    assert reader.list_records("core.devices") == []
