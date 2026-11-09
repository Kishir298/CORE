"""
A.S.C.S. Session Manager for A.S.I.S.

Tracks active and historical ASCS sessions, provides handover state management.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class AscsSessionRecord:
    """Record of an ASCS session."""
    task: str
    mode: str
    workspace: str
    invoke_mode: str
    returncode: int
    stdout: str
    stderr: str
    elapsed_seconds: float
    timestamp: str
    handover_state: dict | None = None


class AscsSessionManager:
    """Manages ASCS session records and handover states."""

    def __init__(self, storage_path: str | None = None):
        if storage_path is None:
            from asis.configuration.settings import settings
            storage_path = str(settings.paths.data / "ascs_sessions.json")

        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._sessions: list[AscsSessionRecord] = []
        self._load()

    def _load(self) -> None:
        """Load sessions from storage."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path) as f:
                    data = json.load(f)
                self._sessions = [AscsSessionRecord(**item) for item in data]
            except Exception:
                self._sessions = []

    def _save(self) -> None:
        """Save sessions to storage."""
        try:
            # Keep only last 100 sessions
            sessions_to_save = self._sessions[-100:]
            with open(self.storage_path, "w") as f:
                json.dump([asdict(s) for s in sessions_to_save], f, indent=2)
        except Exception:
            pass  # Best effort

    def record_session(
        self,
        task: str,
        mode: str,
        workspace: str,
        invoke_mode: str,
        returncode: int,
        stdout: str,
        stderr: str,
        elapsed_seconds: float,
        handover_state: dict | None = None,
    ) -> AscsSessionRecord:
        """Record a new ASCS session."""
        record = AscsSessionRecord(
            task=task,
            mode=mode,
            workspace=workspace,
            invoke_mode=invoke_mode,
            returncode=returncode,
            stdout=stdout[-5000:] if stdout else "",  # Truncate long output
            stderr=stderr[-2000:] if stderr else "",  # Truncate long errors
            elapsed_seconds=elapsed_seconds,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            handover_state=handover_state,
        )

        self._sessions.append(record)
        self._save()
        return record

    def get_recent_sessions(self, limit: int = 10) -> list[dict]:
        """Get recent sessions as dicts."""
        recent = self._sessions[-limit:] if self._sessions else []
        return [asdict(s) for s in reversed(recent)]

    def get_session_by_task(self, task: str) -> AscsSessionRecord | None:
        """Find session by task substring."""
        for session in reversed(self._sessions):
            if task.lower() in session.task.lower():
                return session
        return None

    def get_handover_state(self, task: str) -> dict | None:
        """Get handover state for a task."""
        session = self.get_session_by_task(task)
        if session and session.handover_state:
            return session.handover_state
        return None

    def clear_history(self) -> None:
        """Clear all session history."""
        self._sessions = []
        self._save()

    def get_stats(self) -> dict:
        """Get session statistics."""
        if not self._sessions:
            return {"total": 0, "successful": 0, "failed": 0, "with_handover": 0}

        total = len(self._sessions)
        successful = sum(1 for s in self._sessions if s.returncode == 0)
        failed = total - successful
        with_handover = sum(1 for s in self._sessions if s.handover_state is not None)

        return {
            "total": total,
            "successful": successful,
            "failed": failed,
            "with_handover": with_handover,
        }
