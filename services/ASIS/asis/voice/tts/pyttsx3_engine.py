"""
Local pyttsx3 TTS provider (offline, no API key).

macOS uses NSSpeechSynthesizer, Windows uses SAPI — both via pyttsx3.
Heavy import is lazy so base tests never require it.
"""

from __future__ import annotations

import tempfile
import wave
from pathlib import Path

from asis.errors import TTSError
from asis.logging.logger import get_logger

from ..models import AudioData
from ..providers import TextToSpeechProvider


class Pyttsx3Engine(TextToSpeechProvider):
    """Synthesize ``text -> AudioData`` via local pyttsx3."""

    def __init__(
        self,
        voice: str = "",
        sample_rate: int = 16_000,
        rate: int = 175,
    ) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive.")
        self._voice_requested = (voice or "").strip()
        self._sample_rate = sample_rate
        self._rate = rate
        self._logger = get_logger("voice.tts.pyttsx3")
        try:
            import pyttsx3  # type: ignore
        except ImportError as exc:
            raise TTSError(
                "pyttsx3 is not installed. Install voice extras "
                "(`pip install pyttsx3`) or set ASIS_VOICE_TTS_ENGINE=mock."
            ) from exc
        try:
            self._engine = pyttsx3.init()
        except Exception as exc:
            raise TTSError(f"could not initialize TTS engine: {exc}") from exc
        try:
            self._engine.setProperty("rate", rate)
            if self._voice_requested and self._voice_requested != "male-default":
                for v in self._engine.getProperty("voices") or []:
                    vid = str(getattr(v, "id", ""))
                    vname = str(getattr(v, "name", ""))
                    if (
                        self._voice_requested.casefold()
                        in (vid + " " + vname).casefold()
                    ):
                        self._engine.setProperty("voice", v.id)
                        break
        except Exception as exc:
            self._logger.warning("TTS voice setup warning: %s", exc)

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def stop(self) -> None:
        """Interrupt active speech where supported (pyttsx3 stop, safe)."""
        try:
            self._engine.stop()
        except Exception as exc:
            self._logger.warning("TTS stop warning: %s", exc)

    def synthesize(self, text: str) -> AudioData:
        if not isinstance(text, str) or not text.strip():
            raise TTSError("text must be a non-empty str.")
        tmp = Path(tempfile.mkdtemp(prefix="asis-tts-")) / "out.wav"
        try:
            self._engine.save_to_file(text.strip(), str(tmp))
            self._engine.runAndWait()
        except Exception as exc:
            raise TTSError(f"TTS synthesis failed: {exc}") from exc
        try:
            samples, sample_rate, channels = _read_wav_mono(tmp)
        except Exception as exc:
            raise TTSError(f"could not read synthesized audio: {exc}") from exc
        finally:
            try:
                tmp.unlink(missing_ok=True)
                tmp.parent.rmdir()
            except OSError:
                pass
        return AudioData(
            samples=samples,
            sample_rate=sample_rate or self._sample_rate,
            channels=channels,
            metadata={"engine": "pyttsx3"},
        )


def _read_wav_mono(path: Path) -> tuple[list[float], int, int]:
    """Read a WAV file, return (mono float samples, sample_rate, channels)."""
    with wave.open(str(path), "rb") as wf:
        n_channels = wf.getnchannels()
        sample_rate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)
        sampwidth = wf.getsampwidth()
    import struct

    fmt = {1: "b", 2: "h", 4: "i"}.get(sampwidth)
    if fmt is None:
        raise ValueError(f"unsupported sample width: {sampwidth}")
    count = n_frames * n_channels
    values = struct.unpack("<" + fmt * count, raw)
    scale = float(2 ** (8 * sampwidth - 1))
    mono: list[float] = []
    for i in range(n_frames):
        frame = values[i * n_channels : (i + 1) * n_channels]
        mono.append(sum(float(v) / scale for v in frame) / max(1, n_channels))
    return mono, int(sample_rate), 1
