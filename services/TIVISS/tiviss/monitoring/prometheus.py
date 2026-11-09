"""Prometheus metrics exporter for TIVISS."""

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

# Memory operations
tiviss_memory_operations_total = Counter(
    "tiviss_memory_operations_total",
    "Total memory operations",
    ["operation", "status"],
)
tiviss_memory_latency_seconds = Histogram(
    "tiviss_memory_latency_seconds",
    "Memory operation latency",
    ["operation"],
)
tiviss_memory_entries_total = Gauge(
    "tiviss_memory_entries_total",
    "Total memory entries",
)

# Tool calls
tiviss_tool_calls_total = Counter(
    "tiviss_tool_calls_total",
    "Total tool calls",
    ["tool", "status"],
)
tiviss_tool_latency_seconds = Histogram(
    "tiviss_tool_latency_seconds",
    "Tool call latency",
    ["tool"],
)

# Conversation/handling
tiviss_conversation_turns_total = Counter(
    "tiviss_conversation_turns_total",
    "Total conversation turns",
    ["status"],
)
tiviss_conversation_active = Gauge(
    "tiviss_conversation_active",
    "Active conversations",
)

# Handover
tiviss_handovers_total = Counter(
    "tiviss_handovers_total",
    "Total handovers",
    ["status"],
)

# Export/import
tiviss_export_size_bytes = Histogram(
    "tiviss_export_size_bytes",
    "Export size in bytes",
)
tiviss_import_total = Counter(
    "tiviss_import_total",
    "Total imports",
    ["status"],
)

# Ollama provider
tiviss_ollama_requests_total = Counter(
    "tiviss_ollama_requests_total",
    "Total Ollama requests",
    ["model", "status"],
)
tiviss_ollama_latency_seconds = Histogram(
    "tiviss_ollama_latency_seconds",
    "Ollama request latency",
    ["model"],
)

# Web tools
tiviss_web_searches_total = Counter(
    "tiviss_web_searches_total",
    "Total web searches",
    ["status"],
)
tiviss_web_fetch_total = Counter(
    "tiviss_web_fetch_total",
    "Total web fetches",
    ["status"],
)

# Calculator
tiviss_calculations_total = Counter(
    "tiviss_calculations_total",
    "Total calculations",
    ["operation", "status"],
)

# Voice
tiviss_voice_capture_total = Counter(
    "tiviss_voice_capture_total",
    "Total voice captures",
    ["status"],
)
tiviss_voice_speak_total = Counter(
    "tiviss_voice_speak_total",
    "Total voice syntheses",
    ["status"],
)

# Translation
tiviss_translations_total = Counter(
    "tiviss_translations_total",
    "Total translations",
    ["status"],
)


def metrics_endpoint() -> Response:
    """FastAPI endpoint for Prometheus metrics."""
    from fastapi import Response as FastAPIResponse
    return FastAPIResponse(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )