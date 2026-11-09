"""A.S.C.S. Integration Tool for T.I.V.I.S.S.

Allows T.I.V.I.S.S. to execute coding tasks via A.S.C.S. with handover support.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..permissions.permissions import Permission
from .interface import Tool, ToolResult, ToolStatus


@dataclass
class AscsHandoverState:
    """Serialized ASCS session state for TIVISS takeover."""
    task: str
    plan: Any = None
    completed_actions: list = field(default_factory=list)
    observations: list = field(default_factory=list)
    partial_results: dict = field(default_factory=dict)
    context_index_ref: str = ""
    experience_tags: list = field(default_factory=list)
    workspace: str = ""
    timestamp: str = ""


class AscsIntegrationTool(Tool):
    """Execute coding tasks via A.S.C.S. with optional handover."""

    def __init__(self, settings=None) -> None:
        self._settings = settings
        self._session_manager = None

    @property
    def tool_id(self) -> str:
        return "ascs_integration"

    @property
    def name(self) -> str:
        return "ASCSIntegration"

    @property
    def description(self) -> str:
        return "Execute coding tasks via A.S.C.S. (A Smart Coding System). Supports subprocess and API invocation modes with handover support."

    @property
    def permission(self) -> Permission:
        return Permission.of("tools.coding")

    def _get_settings(self):
        if self._settings is not None:
            return self._settings
        from ..configuration import settings as tiviss_settings
        return tiviss_settings

    def _get_session_manager(self):
        if self._session_manager is None:
            from .ascs_session_manager import AscsSessionManager
            self._session_manager = AscsSessionManager()
        return self._session_manager

    def _build_subprocess_cmd(self, args: dict, settings) -> list[str]:
        """Build the risa CLI command."""

        cmd = ["risa"]

        cmd.append(args["task"])

        mode = args.get("mode", settings.ascs.mode)
        if mode:
            cmd.extend(["--mode", mode])

        workspace = args.get("workspace", settings.ascs.workspace)
        if workspace:
            cmd.extend(["--workspace", workspace])

        model = args.get("model", settings.ascs.model)
        if model:
            cmd.extend(["--model", model])

        intelligence = args.get("intelligence", settings.ascs.intelligence)
        if intelligence:
            cmd.extend(["--intelligence", intelligence])

        max_iter = args.get("max_iterations", settings.ascs.max_iterations)
        if max_iter:
            cmd.extend(["--max-iterations", str(max_iter)])

        req_timeout = settings.ascs.request_timeout
        if req_timeout:
            cmd.extend(["--request-timeout", str(req_timeout)])

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
            return ToolResult(
                tool_id=self.tool_id,
                status=ToolStatus.FAILED,
                error="ASCS integration is disabled. Set ASIS_ASCS_ENABLED=true to enable.",
            )


        task = kwargs.get("task", "")
        if not isinstance(task, str) or not task.strip():
            return ToolResult(
                tool_id=self.tool_id,
                status=ToolStatus.FAILED,
                error="task must be a non-empty string.",
            )

        invoke_mode = kwargs.get("invoke_mode", settings.ascs.invoke_mode)
        if invoke_mode not in ("subprocess", "api"):
            return ToolResult(
                tool_id=self.tool_id,
                status=ToolStatus.FAILED,
                error="invoke_mode must be 'subprocess' or 'api'.",
            )

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
            return ToolResult(
                tool_id=self.tool_id,
                status=ToolStatus.FAILED,
                error=f"Workspace does not exist: {workspace}",
            )

        start_time = time.time()

        if invoke_mode == "subprocess":
            cmd = self._build_subprocess_cmd(cmd_args, settings)
            returncode, stdout, stderr = self._execute_subprocess(cmd, workspace, settings)
        else:
            returncode, stdout, stderr = self._execute_api(cmd_args, settings)

        elapsed = time.time() - start_time

        handover_state = None
        if (settings.ascs.handover_enabled and
            kwargs.get("enable_handover", True) and
            returncode == 0 and
            Path(workspace, ".ascs", "task_state.json").exists()):

            handover_state = self._extract_handover_state(workspace, task)

        session_mgr = self._get_session_manager()
        session_mgr.record_session(
            task=task,
            mode=cmd_args["mode"],
            workspace=workspace,
            invoke_mode=invoke_mode,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            elapsed_seconds=elapsed,
            handover_state=handover_state,
        )

        if returncode == 0:
            return ToolResult(
                tool_id=self.tool_id,
                status=ToolStatus.OK,
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
            )
        else:
            return ToolResult(
                tool_id=self.tool_id,
                status=ToolStatus.FAILED,
                error=f"ASCS execution failed (exit {returncode}): {stderr[:500]}",
            )

    def _extract_handover_state(self, workspace: str, task: str) -> AscsHandoverState | None:
        """Extract handover state from ASCS task_state.json."""

        try:
            task_state_path = Path(workspace) / ".ascs" / "task_state.json"
            if not task_state_path.exists():
                return None

            with open(task_state_path) as f:
                data = json.load(f)

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
    """Receive and process ASCS handover state for TIVISS continuation."""

    def __init__(self, settings=None) -> None:
        self._settings = settings

    @property
    def tool_id(self) -> str:
        return "ascs_handover"

    @property
    def name(self) -> str:
        return "ASCSHandover"

    @property
    def description(self) -> str:
        return "Receive ASCS handover state and continue the task in TIVISS. Loads task graph, context index, and experience tags."

    @property
    def permission(self) -> Permission:
        return Permission.of("tools.coding")

    def _get_settings(self):
        if self._settings is not None:
            return self._settings
        from ..configuration import settings as tiviss_settings
        return tiviss_settings

    def execute(self, **kwargs: Any) -> ToolResult:
        handover_data = kwargs.get("handover_state")
        if not handover_data or not isinstance(handover_data, dict):
            return ToolResult(
                tool_id=self.tool_id,
                status=ToolStatus.FAILED,
                error="handover_state must be a valid object.",
            )

        required = ["task", "workspace", "context_index_ref", "completed_actions", "observations"]
        for field_name in required:
            if field_name not in handover_data:
                return ToolResult(
                    tool_id=self.tool_id,
                    status=ToolStatus.FAILED,
                    error=f"Missing required field in handover_state: {field_name}",
                )

        context_index_path = handover_data.get("context_index_ref")
        context_data = {}
        if context_index_path and Path(context_index_path).exists():
            try:
                with open(context_index_path) as f:
                    context_data = json.load(f)
            except Exception:
                pass

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

        msg = (
            "Received handover from ASCS for task: " + handover_data["task"][:100] +
            ". Completed " + str(len(handover_data["completed_actions"])) +
            " actions. TIVISS can now continue with full context."
        )

        return ToolResult(
            tool_id=self.tool_id,
            status=ToolStatus.OK,
            data={
                "continuation_context": continuation_context,
                "message": msg,
            },
        )

    def _summarize_context_index(self, context_data: dict) -> str:
        """Summarize the ASCS context index for TIVISS prompt."""

        if not context_data:
            return "No context index available."

        files = context_data.get("files", {})
        symbols = context_data.get("symbols", {})

        key_files = list(files.keys())[:10]
        join_str = ", ".join(key_files)
        return (
            "Context index: " + str(len(files)) + " files indexed, " +
            str(len(symbols)) + " symbols extracted. " +
            "Key files: " + join_str
        )


class AscsStatusTool(Tool):
    """Check A.S.C.S. availability and session status."""

    def __init__(self, settings=None) -> None:
        self._settings = settings

    @property
    def tool_id(self) -> str:
        return "ascs_status"

    @property
    def name(self) -> str:
        return "ASCSStatus"

    @property
    def description(self) -> str:
        return "Check A.S.C.S. availability, version, and active sessions."

    @property
    def permission(self) -> Permission:
        return Permission.of("tools.safe")

    def _get_settings(self):
        if self._settings is not None:
            return self._settings
        from ..configuration import settings as tiviss_settings
        return tiviss_settings

    def execute(self, **kwargs: Any) -> ToolResult:
        settings = self._get_settings()
        if not settings.ascs.enabled:
            return ToolResult(
                tool_id=self.tool_id,
                status=ToolStatus.FAILED,
                error="ASCS integration is disabled.",
            )

        result_data = {"enabled": True, "invoke_mode": settings.ascs.invoke_mode}

        if kwargs.get("check_install", True):
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
        return ToolResult(
            tool_id=self.tool_id,
            status=ToolStatus.OK,
            data=result_data,
        )


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
        names.append(tool.tool_id)
    return names