"""
Audio output providers.
"""

try:  # optional heavy dep; never break base imports
    from .sounddevice_output import SoundDeviceOutputProvider
except Exception:  # pragma: no cover - missing optional dep path
    SoundDeviceOutputProvider = None  # type: ignore[assignment]

__all__ = ["SoundDeviceOutputProvider"]
