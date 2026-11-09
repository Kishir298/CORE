"""Tool-router builders + shared ensure helpers (pure wiring, no app state)."""

from __future__ import annotations

import contextlib

from asis.tools.executor import ToolExecutor
from asis.tools.provided import CurrentTimeTool, EchoTool
from asis.tools.registry import ToolRegistry
from asis.tools.router import ToolRouter, build_executor


def build_default_tool_router(
    executor: ToolExecutor | None = None,
) -> ToolRouter:
    """Build the default safe router with the audited built-in tools."""
    from asis.tools.provided import (
        register_calculator_tools,
        register_translation_tools,
        register_web_tools,
    )

    registry = ToolRegistry()
    registry.register(EchoTool())
    registry.register(CurrentTimeTool())
    # Web tools are optional; never break the default router.
    with contextlib.suppress(Exception):
        register_web_tools(registry)
    # Translation tools are optional; never break the default router.
    with contextlib.suppress(Exception):
        register_translation_tools(registry)
    # Calculator tools are optional; never break the default router.
    with contextlib.suppress(Exception):
        register_calculator_tools(registry)
    return ToolRouter(registry=registry, executor=build_executor(executor))


def build_coding_tool_router(
    workspace,
    executor: ToolExecutor | None = None,
) -> ToolRouter:
    """Build the coding router (general tools + workspace-bound coding tools)."""
    from asis.coding.tools import build_coding_registry
    from asis.tools.provided import (
        register_ascs_tools,
        register_calculator_tools,
        register_translation_tools,
        register_web_tools,
    )

    registry = ToolRegistry()
    registry.register(EchoTool())
    registry.register(CurrentTimeTool())
    with contextlib.suppress(Exception):
        register_web_tools(registry)
    with contextlib.suppress(Exception):
        register_translation_tools(registry)
    with contextlib.suppress(Exception):
        register_calculator_tools(registry)
    with contextlib.suppress(Exception):
        register_ascs_tools(registry)
    for tool in build_coding_registry(workspace).list_tools():
        registry.register(tool)
    return ToolRouter(registry=registry, executor=build_executor(executor))


def ensure_core_tools(router: ToolRouter, core) -> None:
    """Register CORE tools on a router once (duplicate-safe)."""
    if core is None or router is None:
        return
    try:
        from asis.tools.provided import register_core_tools
    except Exception:
        return
    # Already registered (or registry rejected) — never fatal.
    with contextlib.suppress(Exception):
        register_core_tools(router.registry, core)


def ensure_web_tools(router: ToolRouter) -> None:
    """Register shared web tools on a router once (duplicate-safe)."""
    if router is None:
        return
    try:
        from asis.tools.provided import register_web_tools
    except Exception:
        return
    # Already registered (or registry rejected) — never fatal.
    with contextlib.suppress(Exception):
        register_web_tools(router.registry)


def ensure_translation_tools(router: ToolRouter) -> None:
    """Register shared translation tools once (duplicate-safe)."""
    if router is None:
        return
    try:
        from asis.tools.provided import register_translation_tools
    except Exception:
        return
    # Already registered (or registry rejected) — never fatal.
    with contextlib.suppress(Exception):
        register_translation_tools(router.registry)


def ensure_calculator_tools(router: ToolRouter) -> None:
    """Register shared calculator tools once (duplicate-safe)."""
    if router is None:
        return
    try:
        from asis.tools.provided import register_calculator_tools
    except Exception:
        return
    # Already registered (or registry rejected) — never fatal.
    with contextlib.suppress(Exception):
        register_calculator_tools(router.registry)


def ensure_all_tools(router: ToolRouter, core=None) -> None:
    """Register all shared tool groups on a router (duplicate-safe)."""
    ensure_core_tools(router, core)
    ensure_web_tools(router)
    ensure_translation_tools(router)
    ensure_calculator_tools(router)
