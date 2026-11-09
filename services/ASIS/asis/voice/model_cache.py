"""
Offline model-missing reporting for A.S.I.S. voice engines.

Real voice engines (STT, speaker, VAD, wake-word) run inference locally,
but their model weights are fetched by the upstream library on first use.
That fetch requires internet at install/setup time — never silently at
runtime: when weights are absent and cannot be retrieved (e.g. offline),
constructors must report ``MODEL_NOT_INSTALLED`` with an actionable hint
instead of a generic load failure, and must never retry or download in
a loop.
"""

from __future__ import annotations


def model_missing_message(
    *,
    engine: str,
    model: str,
    setting: str,
    detail: str = "",
) -> str:
    """Build the ``MODEL_NOT_INSTALLED`` message for a voice engine."""
    suffix = f" ({detail})" if detail else ""
    return (
        f"MODEL_NOT_INSTALLED: {engine} model '{model}' is not available "
        f"locally{suffix}. While online, install voice extras and warm the "
        f"cache once (`pip install -r requirements/voice.txt`, then run the "
        f"engine once with internet access); offline, set {setting}=mock."
    )
