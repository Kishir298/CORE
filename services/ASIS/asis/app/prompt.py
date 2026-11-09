"""Pure prompt-section builders for the assistant context (no I/O)."""

from __future__ import annotations

from .profiles import get_profile


def build_memory_section(query, memory, max_items, logger) -> str:
    """Memory context block for the prompt (fail-open, bounded)."""
    if not query or not query.strip():
        return ""
    try:
        search = getattr(memory, "search_context", None)
        if callable(search):
            return search(query, limit=max_items) or ""
        return ""
    except Exception as exc:
        logger.warning("Memory retrieval failed, continuing: %s", exc)
        return ""


def build_mode_section(mode) -> str:
    """Mode instructions for the labeled MODE context block."""
    try:
        return get_profile(mode).instructions.strip()
    except Exception:
        return ""


def build_capabilities_section(tool_names: list) -> str:
    """Bounded capabilities summary + active tool names (no schemas)."""
    try:
        from asis.identity.personality import CAPABILITY_SUMMARY
    except Exception:
        CAPABILITY_SUMMARY = ""
    names = list(tool_names)
    # Bound tool list so capabilities never bloat the prompt.
    shown = ", ".join(names[:24])
    if len(names) > 24:
        shown += f" (+{len(names) - 24} more)"
    caps = CAPABILITY_SUMMARY.strip()
    tool_line = f"Tools: {shown}" if shown else ""
    parts = [p for p in (caps, tool_line) if p]
    text = "\n".join(parts)
    return text[:2000]


def build_constraints_section(plan) -> str:
    """Per-turn orchestrator constraints (empty outside a planned turn)."""
    if plan is None:
        return ""
    lines = [c.strip() for c in (plan.response_constraints or ()) if c.strip()]
    return "\n".join(f"- {line}" for line in lines[:8])
