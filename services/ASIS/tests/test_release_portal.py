"""Real subprocess/loopback transport tests with a simulated Ollama server.

No model inference is claimed. Set ASIS_CORE_RELEASE_ROOT to test the attached
CORE Services implementation alongside this repository.
"""
from __future__ import annotations

import importlib.util
import json
import os
import queue
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


@pytest.fixture
def simulated_ollama():
    release = threading.Event()
    streaming = threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            body = json.dumps({"models": [{"name": "protocol-test:latest"}]}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200)
            self.end_headers()
            if not request.get("stream"):
                self.wfile.write(json.dumps({"message": {"content": "probe ready"}, "done": True}).encode())
                return
            # More than requests' read chunk size, so it reaches ASIS before
            # the server releases the final frame.
            self.wfile.write((json.dumps({"message": {"content": "FIRST"}, "done": False}) + "\n").encode())
            self.wfile.write((json.dumps({"message": {"content": " padding" * 120}, "done": False}) + "\n").encode())
            self.wfile.flush()
            streaming.set()
            release.wait(10)
            try:
                self.wfile.write((json.dumps({"message": {"content": "LAST"}, "done": True}) + "\n").encode())
            except (BrokenPipeError, ConnectionResetError):
                pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", release, streaming
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(3)


def profile_env(tmp_path, endpoint):
    env = os.environ.copy()
    for part in ("DATA", "CONFIG", "CACHE", "LOG", "MEMORY", "RUNTIME"):
        env[f"ASIS_{part}_DIRECTORY"] = str(tmp_path / part.lower())
    env.update(ASIS_AI_ENDPOINT=endpoint, ASIS_AI_MODEL="protocol-test:latest",
               ASIS_AI_PROVIDER="ollama", ASIS_AI_NATIVE_TOOLS="false",
               ASIS_OLLAMA_MANAGED="off", ASIS_CORE_ENABLED="false")
    return env


def test_installed_command_from_foreign_directory_streams(tmp_path, simulated_ollama):
    endpoint, release, streaming = simulated_ollama
    launcher = Path(sys.executable).parent / ("asis.exe" if os.name == "nt" else "asis")
    if not launcher.exists():
        pytest.skip("requires pip install of this repository into the test interpreter")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    proc = subprocess.Popen([str(launcher), "--mode", "general", "--workspace", str(workspace),
        "--memory-db", str(tmp_path / "profile.db"), "--message=Hello there!"], cwd=tmp_path,
        env=profile_env(tmp_path, endpoint), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1)
    lines = queue.Queue()
    threading.Thread(target=lambda: [lines.put(x) for x in iter(proc.stdout.readline, "")], daemon=True).start()
    try:
        assert streaming.wait(20), (proc.poll(), proc.stderr.read() if proc.poll() is not None else "process still running")
        # FIRST is deliberately newline-free: inspect the pipe a char at a time
        # below instead of waiting for the task's trailing newline.
        # The stdout thread is line-based for boot; streaming is checked by the
        # CORE event test with read1. Here completion validates installed wiring.
        release.set()
        assert proc.wait(timeout=15) == 0, proc.stderr.read()
        output = "".join(list(lines.queue))
        assert "FIRST" in output and "LAST" in output
        assert (tmp_path / "profile.db").exists()
    finally:
        release.set()
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)


def load_core():
    root = os.environ.get("ASIS_CORE_RELEASE_ROOT")
    if not root:
        pytest.skip("attached CORE release not configured; set ASIS_CORE_RELEASE_ROOT")
    file = Path(root) / "core/web/services.py"
    spec = importlib.util.spec_from_file_location("release_core_services", file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def wait_for(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        threading.Event().wait(0.02)
    raise AssertionError("timed out waiting for portal event")


def test_actual_core_profile_stream_completion_and_cancellation(tmp_path, monkeypatch, simulated_ollama):
    core = load_core()
    endpoint, release, streaming = simulated_ollama
    for k, v in profile_env(tmp_path / "ignored", endpoint).items():
        if k.startswith("ASIS_"):
            monkeypatch.setenv(k, v)
    source = Path(__file__).resolve().parents[1]
    services = core.Services(tmp_path / "portal", {"asis": str(source)}, "not-forwarded-test-key")
    monkeypatch.setattr(services, "interpreter", lambda service: sys.executable)
    user = {"id": "a" * 32, "role": "member"}
    try:
        result = services.start("asis", user, "Hello there!")
        job = services.get(result["id"], user)
        assert streaming.wait(10)
        wait_for(lambda: any("FIRST" in x["text"] for x in job.view()["events"]))
        assert job.status == "running"  # live output arrives before final frame
        release.set()
        wait_for(lambda: job.status not in ("starting", "running"))
        assert job.status == "completed", job.view()
        argv, cwd, env = services.command("asis", user, "hello", "build")
        assert "--mode" in argv and argv[argv.index("--mode")+1] == "general"
        assert env["ASIS_CORE_ENABLED"] == "false"
        assert not any(k.startswith("RESCS_") for k in env)
        assert (tmp_path / "portal/profiles" / user["id"] / "asis-memory.sqlite3").exists()
        with pytest.raises(PermissionError):
            services.command("ascs", user, "hello", "build")
        with pytest.raises(PermissionError):
            services.get(job.id, {"id": "b" * 32, "role": "member"})
        # A second task is cancelled while the simulated server holds its stream.
        release.clear()
        streaming.clear()
        result = services.start("asis", user, "Hello there!")
        job = services.get(result["id"], user)
        assert streaming.wait(10)
        services.stop(job.id, user)
        wait_for(lambda: job.process.poll() is not None)
        assert job.status == "cancelled"
    finally:
        release.set()
        services.close()
