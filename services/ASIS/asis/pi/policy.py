"""Fail-closed Linux resource admission. No model downloads or cloud fallback."""
from __future__ import annotations

import json
import math
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

GIB = 1024**3
TIERS = {"small": (0.7, 2.5, 1.5), "initial": (1.8, 3.5, 2.5), "ceiling": (3.3, 5.0, 4.0)}


class PolicyError(RuntimeError):
    pass


def enabled():
    return os.getenv("ASIS_DEPLOYMENT_PROFILE", "").lower() == "pi"


def number(value, name):
    if isinstance(value, bool):
        raise PolicyError(f"Invalid {name}")
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise PolicyError(f"Invalid {name}") from None
    if not math.isfinite(result) or result < 0:
        raise PolicyError(f"Invalid {name}")
    return result


@dataclass
class Snapshot:
    available: int
    cpu_percent: float
    load_per_core: float
    memory_pressure: float
    temperature_c: float | None
    cgroup_remaining: int | None = None


def _cpu(proc):
    fields = [int(x) for x in (proc / "stat").read_text().splitlines()[0].split()[1:9]]
    return sum(fields), fields[3] + fields[4]


def snapshot(proc=Path("/proc"), cgroup=Path("/sys/fs/cgroup"), thermal=Path("/sys/class/thermal"), sample_seconds=10):
    if sys.platform != "linux":
        raise PolicyError("Pi resource admission requires Linux; standalone mode is unchanged.")
    try:
        first = _cpu(proc)
        time.sleep(sample_seconds)
        second = _cpu(proc)
        total = second[0] - first[0]
        if total <= 0:
            raise ValueError("CPU interval unavailable")
        cpu = 100 * (1 - (second[1] - first[1]) / total)
        mem = dict(line.split(":", 1) for line in (proc / "meminfo").read_text().splitlines())
        available = int(mem["MemAvailable"].split()[0]) * 1024
        load = float((proc / "loadavg").read_text().split()[0]) / max(1, os.cpu_count() or 1)
        pressure = (proc / "pressure/memory").read_text()
        psi = float(re.search(r"some avg10=([\d.]+)", pressure)[1])
        # cgroup v2: effective budget is the tightest finite ancestor limit.
        relative = next(line.split(":", 2)[2] for line in (proc / "self/cgroup").read_text().splitlines() if line.startswith("0::"))
        folder = (cgroup / relative.lstrip("/")).resolve()
        if not folder.is_relative_to(cgroup.resolve()):
            raise ValueError("invalid cgroup path")
        remaining = []
        while True:
            limit_path = folder / "memory.max"
            if limit_path.exists():
                value = limit_path.read_text().strip()
                if value != "max":
                    used = int((folder / "memory.current").read_text())
                    remaining.append(max(0, int(value) - used))
            if folder == cgroup.resolve():
                break
            folder = folder.parent
        bound = min(remaining) if remaining else None
        if bound is not None:
            available = min(available, bound)
        temps = [int(p.read_text()) / 1000 for p in thermal.glob("thermal_zone*/temp")]
        return Snapshot(available, cpu, load, psi, max(temps) if temps else None, bound)
    except (OSError, ValueError, KeyError, StopIteration, TypeError) as exc:
        raise PolicyError("Linux resource telemetry unavailable; admission blocked.") from exc


def manifest_path():
    from asis.configuration import settings
    return Path(os.getenv("ASIS_PI_MODEL_MANIFEST", str(settings.paths.config / "pi-models.json")))


def approval(model):
    try:
        record = json.loads(manifest_path().read_text())[model]
        tier = TIERS[record["tier"]]
        if not re.fullmatch(r"(?:sha256:)?[a-f0-9]{64}", record["digest"]):
            raise ValueError("digest")
        peak = max(tier[2], number(record["peak_gib"], "peak_gib"), number(record.get("observed_peak_gib", 0), "observed_peak_gib") * 1.2)
        context = record.get("context", 2048)
        if context not in (2048, 4096) or isinstance(context, bool):
            raise ValueError("context")
        if (record["tier"] == "ceiling" or context == 4096) and record.get("benchmark_verified") is not True:
            raise ValueError("benchmark required")
        if ":" not in model:
            raise ValueError("explicit model tag required")
        return record, peak, context
    except (OSError, KeyError, ValueError, TypeError) as exc:
        raise PolicyError("Model is not explicitly approved: configure the owner-controlled Pi manifest with exact tag/digest and measured policy.") from exc


def decide(s, record, peak, resident=0):
    for name in ("available", "cpu_percent", "load_per_core", "memory_pressure"):
        number(getattr(s, name), name)
    if s.temperature_c is None:
        raise PolicyError("Thermal telemetry unavailable; Pi admission blocked")
    number(s.temperature_c, "temperature_c")
    number(resident, "resident")
    number(peak, "peak")
    gate = TIERS[record["tier"]][1]
    needed = max(0, peak * GIB - resident)
    report = {"status": "allowed", "reason": "resource gates satisfied; quality still requires benchmarking",
              "resources": asdict(s), "reserve_gib": 1.5, "additional_peak_gib": needed / GIB,
              "context": record.get("context", 2048)}
    if s.available + resident < gate * GIB or needed > s.available - 1.5 * GIB:
        report.update(status="blocked", reason="insufficient effective RAM; select an approved smaller model explicitly")
    elif s.cpu_percent > 70 or s.load_per_core > 1 or s.memory_pressure > 10 or (s.temperature_c is not None and s.temperature_c >= 80):
        report.update(status="queued", reason="CPU/load/memory/thermal pressure; websites take priority")
    return report
