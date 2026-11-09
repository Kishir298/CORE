"""Cooperative cross-process queue and pinned Ollama contract verification."""
from __future__ import annotations

import contextlib
import functools
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener

from .policy import TIERS, PolicyError, approval, decide, enabled, snapshot


def request(host, path, body=None):
    parsed = urlparse(host)
    if parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1", "::1") or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise PolicyError("Pi inference is loopback-only. A remote endpoint needs a separately reviewed deployment policy.")
    try:
        # Never follow redirects to another service or remote machine.
        from urllib.request import HTTPRedirectHandler
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                raise PolicyError("Ollama redirects are refused")
        opener = build_opener(ProxyHandler({}), NoRedirect())
        req = Request(host.rstrip("/") + path, data=json.dumps(body).encode() if body is not None else None,
                      headers={"Content-Type": "application/json"})
        with opener.open(req, timeout=5) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("oversize response")
        result = json.loads(raw)
        if not isinstance(result, dict) or result.get("error"):
            raise ValueError("invalid response")
        return result
    except (OSError, ValueError) as exc:
        raise PolicyError("Ollama metadata request failed; no model substitution or download performed.") from exc


def model_info(host, model, record):
    tags = request(host, "/api/tags").get("models", [])
    tag = next((x for x in tags if x.get("name") == model), None)
    if not tag or tag.get("digest", "").removeprefix("sha256:") != record["digest"].removeprefix("sha256:"):
        raise PolicyError("Exact installed model tag/digest does not match the approved manifest.")
    info = request(host, "/api/show", {"model": model})
    details = info.get("details", {})
    match = re.fullmatch(r"([\d.]+)\s*([BM])", str(details.get("parameter_size", "")), re.I)
    size = float(match[1]) / (1000 if match[2].upper() == "M" else 1) if match else float("inf")
    if size > TIERS[record["tier"]][0] or not str(details.get("quantization_level", "")).upper().startswith("Q"):
        raise PolicyError("Model size/quantization does not match an allowed Pi tier (7B+ is never automatically admitted).")
    if "completion" not in info.get("capabilities", []):
        raise PolicyError("Model chat/completion capability could not be verified.")
    return info


def queue_directory():
    # One host-owned directory for all ASIS/ASCS/member jobs, outside per-user data.
    return Path(os.getenv("ASIS_PI_QUEUE_DIRECTORY", "/run/risarms-ai"))


def publish(directory, report):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = directory / ("status-" + uuid.uuid4().hex)
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(report, stream)
        temp.replace(directory / "status.json")
    finally:
        temp.unlink(missing_ok=True)


@contextlib.contextmanager
def lease(model, host):
    if sys.platform != "linux":
        raise PolicyError("The Pi queue adapter requires Linux")
    import fcntl
    directory = queue_directory()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    record, peak, context = approval(model)
    bound = 180.0
    deadline = time.monotonic() + bound
    fd = os.open(directory / "inference.lock", os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    admitted = False
    report = None
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise PolicyError("Shared inference queue timed out; no action was started")
                print("AI queued: another shared inference job is active.", file=sys.stderr, flush=True)
                time.sleep(1)
        info = model_info(host, model, record)
        running = request(host, "/api/ps").get("models", [])
        for loaded in running:
            if loaded.get("digest", "").removeprefix("sha256:") != record["digest"].removeprefix("sha256:"):
                request(host, "/api/generate", {"model": loaded["name"], "keep_alive": 0, "stream": False})
        running = request(host, "/api/ps").get("models", [])
        if any(x.get("digest", "").removeprefix("sha256:") != record["digest"].removeprefix("sha256:") for x in running):
            raise PolicyError("Previous model is still resident; safe switching blocked")
        resident = sum(int(x.get("size", 0)) for x in running)
        while True:
            report = decide(snapshot(), record, peak, resident)
            report.update(model=model, digest=record["digest"], threads=2)
            publish(directory, report)
            if report["status"] == "allowed":
                break
            if report["status"] == "blocked" or time.monotonic() >= deadline:
                raise PolicyError(report["reason"])
            print("AI queued: " + report["reason"], file=sys.stderr, flush=True)
            time.sleep(1)
        admitted = True
        yield context, info, record
        publish(directory, {"status": "idle", "model": model, "context": context, "reason": "completed; lease released"})
    except BaseException as exc:
        # A waiter must not overwrite the running worker's status.
        if acquired:
            failure = dict(report or {})
            failure.update(status="cancelled" if isinstance(exc, (KeyboardInterrupt, SystemExit, GeneratorExit)) else "failed",
                           model=model, reason=str(exc) if isinstance(exc, PolicyError) else "AI job stopped; no automatic replay")
            publish(directory, failure)
        raise
    finally:
        # Best-effort unload under the same lock before the next worker enters.
        if admitted:
            try:
                request(host, "/api/generate", {"model": model, "keep_alive": 0, "stream": False})
            except Exception:
                pass
        if acquired:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def guarded(function):
    """Lease spans the complete response, including consumption of a stream."""
    @functools.wraps(function)
    def wrapper(self, *args, **kwargs):
        if not enabled():
            return function(self, *args, **kwargs)
        def run():
            with lease(self.model, self.host) as (context, info, record):
                self._pi_options = {"num_ctx": context, "num_thread": 2}
                self._pi_tools = record.get("tools_verified") is True and "tools" in info.get("capabilities", [])
                saved_retries = self.retries
                self.retries = 0
                try:
                    if function.__name__ == "chat_with_tools" and not self._pi_tools:
                        raise PolicyError("Native tool protocol not verified for this model")
                    result = function(self, *args, **kwargs)
                    if function.__name__ == "stream_chat":
                        yield from result
                    else:
                        yield result
                finally:
                    self._pi_options = None
                    self.retries = saved_retries
        if function.__name__ == "stream_chat":
            return run()
        return list(run())[0]
    return wrapper
