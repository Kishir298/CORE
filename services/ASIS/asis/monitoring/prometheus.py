"""Prometheus metrics exporter for ASIS."""

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

# Tool execution metrics
asis_tool_executions_total = Counter(
    "asis_tool_executions_total",
    "Total tool executions",
    ["tool", "status"],
)
asis_tool_latency_seconds = Histogram(
    "asis_tool_latency_seconds",
    "Tool execution latency",
    ["tool"],
)

# ASCS integration metrics
asis_ascs_invocations_total = Counter(
    "asis_ascs_invocations_total",
    "Total ASCS invocations",
    ["invoke_mode", "status"],
)
asis_ascs_handover_total = Counter(
    "asis_ascs_handover_total",
    "Total ASCS handovers",
    ["status"],
)

# LLM/Ollama metrics
asis_ollama_requests_total = Counter(
    "asis_ollama_requests_total",
    "Total Ollama requests",
    ["model", "status"],
)
asis_ollama_latency_seconds = Histogram(
    "asis_ollama_latency_seconds",
    "Ollama request latency",
    ["model"],
)

# Conversation metrics
asis_conversation_turns_total = Counter(
    "asis_conversation_turns_total",
    "Total conversation turns",
    ["mode", "status"],
)
asis_conversation_active = Gauge(
    "asis_conversation_active",
    "Active conversations",
)

# Voice pipeline metrics
asis_voice_capture_total = Counter(
    "asis_voice_capture_total",
    "Total voice captures",
    ["status"],
)
asis_voice_stt_latency_seconds = Histogram(
    "asis_voice_stt_latency_seconds",
    "STT latency",
)
asis_voice_tts_latency_seconds = Histogram(
    "asis_voice_tts_latency_seconds",
    "TTS latency",
)
asis_voice_synthesis_total = Counter(
    "asis_voice_synthesis_total",
    "Total voice syntheses",
    ["status"],
)

# Identity/calibration metrics
asis_identities_total = Gauge(
    "asis_identities_total",
    "Total identities stored",
)
asis_calibration_runs_total = Counter(
    "asis_calibration_runs_total",
    "Total calibration runs",
    ["status"],
)

# Web search/fetch metrics
asis_web_searches_total = Counter(
    "asis_web_searches_total",
    "Total web searches",
    ["status"],
)
asis_web_fetch_total = Counter(
    "asis_web_fetch_total",
    "Total web fetches",
    ["status"],
)

# Calculator metrics
asis_calculator_evaluations_total = Counter(
    "asis_calculator_evaluations_total",
    "Total calculator evaluations",
    ["status"],
)


def metrics_endpoint() -> Response:
    """FastAPI endpoint for Prometheus metrics."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )