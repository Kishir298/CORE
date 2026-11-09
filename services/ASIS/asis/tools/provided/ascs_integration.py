"""
A.S.C.S. Integration Tool for A.S.I.S.

Allows A.S.I.S. to execute coding tasks via A.S.C.S. with two invocation modes:
- subprocess: Runs `risa` CLI command (clean isolation, captures stdout/stderr/exit codes)
- api: Uses Python API directly (better event streaming, requires shared venv)

Supports handover protocol for ASCS -> ASIS session continuation.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from asis.permissions.models import PermissionLevel

from ..base import Tool, ToolMetadata
from ..result import ToolResult


@dataclass
class AscsHandoverState:
    """Serialized ASCS session state for ASIS takeover."""
    task: str
    plan: dict | None
    completed_actions: list
    observations: list
    partial_results: dict
    context_index_ref: str
    experience_tags: list[str]
    workspace: str
    timestamp: str


class AscsIntegrationTool(Tool):
    """Execute coding tasks via A.S.C.S. with optional handover."""

    metadata = ToolMetadata(
        name="ascs_integration",
        description=(
            "Execute coding tasks via A.S.C.S. (A Smart Coding System). "
            "Supports subprocess and API invocation modes with handover support."
        ),
        category="coding",
        permission=PermissionLevel.HIGH,
        tags=("coding", "ascs", "integration", "handover"),
        parameters={
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "The coding task to execute"},
                "mode": {"type": "string", "enum": ["PLAN", "BUILD", "AUTO"], "default": "AUTO"},
                "intelligence": {"type": "string", "enum": ["low", "medium", "high", "xhigh"], "default": "high"},
                "workspace": {"type": "string", "description": "Repository/workspace path"},
                "invoke_mode": {"type": "string", "enum": ["subprocess", "api"], "default": "subprocess"},
                "model": {"type": "string", "description": "Ollama model to use"},
                "max_iterations": {"type": "integer", "default": 50},
                "enable_handover": {"type": "boolean", "default": True},
            },
            "required": ["task"],
        },
    )

    def __init__(self, settings=None) -> None:
        self._settings = settings
        self._session_manager = None

    def _get_settings(self):
        if self._settings is not None:
            return self._settings
        from asis.configuration.settings import settings
        return settings

    def _get_session_manager(self):
        if self._session_manager is None:
            from .ascs_session_manager import AscsSessionManager
            self._session_manager = AscsSessionManager()
        return self._session_manager

    def _build_subprocess_cmd(self, args: dict, settings) -> list[str]:
        """Build the risa CLI command."""
        cmd = ["risa"]

        # Add task
        cmd.append(args["task"])

        # Mode
        mode = args.get("mode", settings.ascs.mode)
        if mode:
            cmd.extend(["--mode", mode])

        # Workspace
        workspace = args.get("workspace", settings.ascs.workspace)
        if workspace:
            cmd.extend(["--workspace", workspace])

        # Model
        model = args.get("model", settings.ascs.model)
        if model:
            cmd.extend(["--model", model])

        # Intelligence
        intelligence = args.get("intelligence", settings.ascs.intelligence)
        if intelligence:
            cmd.extend(["--intelligence", intelligence])

        # Max iterations
        max_iter = args.get("max_iterations", settings.ascs.max_iterations)
        if max_iter:
            cmd.extend(["--max-iterations", str(max_iter)])

        # Request timeout
        req_timeout = settings.ascs.request_timeout
        if req_timeout:
            cmd.extend(["--request-timeout", str(req_timeout)])

        # Command timeout
        cmd_timeout = settings.ascs.command_timeout
        if cmd_timeout:
            cmd.extend(["--command-timeout", str(cmd_timeout)])

        return cmd

    def _execute_subprocess(self, cmd: list[str], workspace: str, settings) -> tuple[int, str, str]:
        """Execute risa command via subprocess."""
        env = os.environ.copy()
        env["RISALIVE"] = "0"  # Ensure no live tests

        try:
            result = subprocess.run(
                cmd,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=settings.ascs.request_timeout * 2,
                env=env,
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", f"Timeout after {settings.ascs.request_timeout * 2}s"
        except FileNotFoundError:
            return -1, "", "risa command not found. Ensure ASCS is installed and in PATH."
        except Exception as e:
            return -1, "", f"Subprocess error: {e}"

    def _execute_api(self, args: dict, settings) -> tuple[int, str, str]:
        """Execute via ASCS Python API."""
        try:
            # Import ASCS modules
            sys.path.insert(0, str(Path(settings.ascs.workspace).parent / "ASCS"))

            from agent.config import load_config
            from agent.core.loop import run_graph_agent
            from agent.models.client import OllamaClient

            config = load_config(
                workspace=args.get("workspace", settings.ascs.workspace),
                mode=args.get("mode", settings.ascs.mode),
                model=args.get("model", settings.ascs.model),
                intelligence=args.get("intelligence", settings.ascs.intelligence),
                max_iterations=args.get("max_iterations", settings.ascs.max_iterations),
                request_timeout=settings.ascs.request_timeout,
                command_timeout=settings.ascs.command_timeout,
            )

            client = OllamaClient(
                base_url=config.ollama_base_url,
                model=config.model,
                request_timeout=config.request_timeout,
            )

            # Run with event sink to capture output
            output_lines = []
            def log_capture(msg):
                output_lines.append(msg)

            result = run_graph_agent(
                config, client, args["task"],
                log=log_capture,
            )

            return 0 if result.is_complete else 1, "\n".join(output_lines), result.error

        except ImportError as e:
            return -1, "", f"ASCS modules not available: {e}. Use subprocess mode."
        except Exception as e:
            return -1, "", f"API execution error: {e}"

    def execute(self, **kwargs: Any) -> ToolResult:
        settings = self._get_settings()

        if not settings.ascs.enabled:
            return ToolResult.failure(
                error="ASCS integration is disabled. Set ASIS_ASCS_ENABLED=true to enable.",
                tool_name=self.name,
            )

        task = kwargs.get("task", "")
        if not isinstance(task, str) or not task.strip():
            return ToolResult.failure(
                error="'task' must be a non-empty string.",
                tool_name=self.name,
            )

        invoke_mode = kwargs.get("invoke_mode", settings.ascs.invoke_mode)
        if invoke_mode not in ("subprocess", "api"):
            return ToolResult.failure(
                error="'invoke_mode' must be 'subprocess' or 'api'.",
                tool_name=self.name,
            )

        # Build command arguments
        cmd_args = {
            "task": task.strip(),
            "mode": kwargs.get("mode", settings.ascs.mode),
            "intelligence": kwargs.get("intelligence", settings.ascs.intelligence),
            "workspace": kwargs.get("workspace", settings.ascs.workspace or os.getcwd()),
            "model": kwargs.get("model", settings.ascs.model),
            "max_iterations": kwargs.get("max_iterations", settings.ascs.max_iterations),
        }

        workspace = cmd_args["workspace"]
        if not Path(workspace).exists():
            return ToolResult.failure(
                error=f"Workspace does not exist: {workspace}",
                tool_name=self.name,
            )

        # Execute
        start_time = time.time()

        if invoke_mode == "subprocess":
            cmd = self._build_subprocess_cmd(cmd_args, settings)
            returncode, stdout, stderr = self._execute_subprocess(cmd, workspace, settings)
        else:
            returncode, stdout, stderr = self._execute_api(cmd_args, settings)

        elapsed = time.time() - start_time

        # Handle handover if enabled and ASCS completed
        handover_state = None
        if (settings.ascs.handover_enabled and
            kwargs.get("enable_handover", True) and
            returncode == 0 and
            Path(workspace, ".ascs", "task_state.json").exists()):

            handover_state = self._extract_handover_state(workspace, task)

        # Record session
        session_mgr = self._get_session_manager()
        session_mgr.record_session(
            task=task,
            mode=cmd_args["mode"],
            workspace=workspace,
            invoke_mode=invoke_mode,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            elapsed=elapsed,
            handover_state=handover_state,
        )

        if returncode == 0:
            return ToolResult.ok(
                data={
                    "task": task,
                    "mode": cmd_args["mode"],
                    "workspace": workspace,
                    "invoke_mode": invoke_mode,
                    "stdout": stdout,
                    "stderr": stderr,
                    "elapsed_seconds": round(elapsed, 2),
                    "handover_state": asdict(handover_state) if handover_state else None,
                },
                tool_name=self.name,
            )
        else:
            return ToolResult.failure(
                error=f"ASCS execution failed (exit {returncode}): {stderr[:500]}",
                tool_name=self.name,
            )

    def _extract_handover_state(self, workspace: str, task: str) -> AscsHandoverState | None:
        """Extract handover state from ASCS task_state.json."""
        try:
            task_state_path = Path(workspace) / ".ascs" / "task_state.json"
            if not task_state_path.exists():
                return None

            with open(task_state_path) as f:
                data = json.load(f)

            # Extract relevant fields
            return AscsHandoverState(
                task=task,
                plan=data.get("plan"),
                completed_actions=data.get("completed_actions", []),
                observations=data.get("observations", []),
                partial_results=data.get("partial_results", {}),
                context_index_ref=str(Path(workspace) / ".ascs" / "context_index.json"),
                experience_tags=data.get("experience_tags", []),
                workspace=workspace,
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            )
        except Exception:
            return None


class AscsHandoverTool(Tool):
    """Receive and process ASCS handover state for ASIS continuation."""

    def __init__(self, settings=None) -> None:
        self._settings = settings

    metadata = ToolMetadata(
        name="ascs_handover",
        description=(
            "Receive ASCS handover state and continue the task in ASIS. "
            "Loads task graph, context index, and experience tags."
        ),
        category="coding",
        permission=PermissionLevel.HIGH,
        tags=("coding", "ascs", "handover"),
        parameters={
            "type": "object",
            "properties": {
                "handover_state": {"type": "object", "description": "ASCS handover state object"},
                "continue_in_asis": {"type": "boolean", "default": True},
            },
            "required": ["handover_state"],
        },
    )

    def execute(self, **kwargs: Any) -> ToolResult:
        handover_data = kwargs.get("handover_state")
        if not handover_data or not isinstance(handover_data, dict):
            return ToolResult.failure(
                error="'handover_state' must be a valid object.",
                tool_name=self.name,
            )

        # Validate required fields
        required = ["task", "workspace", "context_index_ref", "completed_actions", "observations"]
        for field in required:
            if field not in handover_data:
                return ToolResult.failure(
                    error=f"Missing required field in handover_state: {field}",
                    tool_name=self.name,
                )

        # Load context index
        context_index_path = handover_data.get("context_index_ref")
        context_data = {}
        if context_index_path and Path(context_index_path).exists():
            try:
                with open(context_index_path) as f:
                    context_data = json.load(f)
            except Exception:
                pass

        # Build continuation context for ASIS
        continuation_context = {
            "original_task": handover_data["task"],
            "workspace": handover_data["workspace"],
            "completed_actions": handover_data["completed_actions"],
            "observations": handover_data["observations"],
            "partial_results": handover_data.get("partial_results", {}),
            "experience_tags": handover_data.get("experience_tags", []),
            "context_index_summary": self._summarize_context_index(context_data),
            "timestamp": handover_data.get("timestamp"),
        }

        return ToolResult.ok(
            data={
                "continuation_context": continuation_context,
                "message": (
                    f"Received handover from ASCS for task: {handover_data['task'][:100]}. "
                    f"Completed {len(handover_data['completed_actions'])} actions. "
                    f"ASIS can now continue with full context."
                ),
            },
            tool_name=self.name,
        )

    def _summarize_context_index(self, context_data: dict) -> str:
        """Summarize the ASCS context index for ASIS prompt."""
        if not context_data:
            return "No context index available."

        files = context_data.get("files", {})
        symbols = context_data.get("symbols", {})

        return (
            f"Context index: {len(files)} files indexed, "
            f"{len(symbols)} symbols extracted. "
            f"Key files: {', '.join(list(files.keys())[:10])}"
        )


class AscsStatusTool(Tool):
    """Check ASCS availability and session status."""

    def __init__(self, settings=None) -> None:
        self._settings = settings

    metadata = ToolMetadata(
        name="ascs_status",
        description="Check A.S.C.S. availability, version, and active sessions.",
        category="coding",
        permission=PermissionLevel.LOW,
        tags=("coding", "ascs", "status"),
        parameters={
            "type": "object",
            "properties": {
                "check_install": {"type": "boolean", "default": True},
                "list_sessions": {"type": "boolean", "default": True},
            },
        },
    )

    def execute(self, **kwargs: Any) -> ToolResult:
        settings = self._get_settings() if hasattr(self, '_get_settings') else None
        if settings is None:
            from asis.configuration.settings import settings

        if not settings.ascs.enabled:
            return ToolResult.failure(
                error="ASCS integration is disabled.",
                tool_name=self.name,
            )

        result_data = {"enabled": True, "invoke_mode": settings.ascs.invoke_mode}

        if kwargs.get("check_install", True):
            # Check if risa is available
            try:
                proc = subprocess.run(["risa", "--version"], capture_output=True, text=True, timeout=5)
                result_data["risa_available"] = proc.returncode == 0
                result_data["risa_version"] = proc.stdout.strip() if proc.returncode == 0 else "unknown"
            except Exception:
                result_data["risa_available"] = False
                result_data["risa_version"] = "not found"

        if kwargs.get("list_sessions", True):
            session_mgr = self._get_session_manager()
            result_data["sessions"] = session_mgr.get_recent_sessions(10)

        return ToolResult.ok(data=result_data, tool_name=self.name)

    def _get_settings(self):
        from asis.configuration.settings import settings
        return settings

    def _get_session_manager(self):
        from .ascs_session_manager import AscsSessionManager
        return AscsSessionManager()


def build_ascs_tools(settings=None) -> list[Tool]:
    """Build ASCS integration tools."""
    return [
        AscsIntegrationTool(settings),
        AscsHandoverTool(settings),
        AscsStatusTool(settings),
    ]


def register_ascs_tools(registry, settings=None) -> list[str]:
    """Register ASCS tools on registry."""
    names: list[str] = []
    for tool in build_ascs_tools(settings):
        registry.register(tool)
        names.append(tool.name)
    return names
