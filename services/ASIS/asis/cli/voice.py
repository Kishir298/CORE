"""
``asis voice`` runtime: real voice loop with clean lifecycle/shutdown.

Flow: config -> identity -> voice providers -> audio start -> loop
(listen/VAD/wake/STT/speaker -> A.S.I.S. chat -> TTS/output) until
shutdown phrase / Ctrl-C / max-turns. All providers come from the
factory; failures produce structured errors, never tracebacks (unless
--debug). Voice never executes shell; text routes through A.S.I.S.
intelligence (AIManager + memory), where tool permissions apply.
"""

from __future__ import annotations

import argparse
import contextlib
import sys

from asis.ai import AIManager
from asis.configuration import settings
from asis.errors import ASISError
from asis.events import EventBus
from asis.identity import build_identity
from asis.logging.logger import get_logger
from asis.system.interrupt import InterruptCoordinator
from asis.voice.engines.mock import (
    MockAudioInput,
    MockAudioOutput,
    MockSpeakerIdentifier,
    MockSpeechRecognizer,
    MockTextToSpeech,
    MockVadDetector,
    MockWakeWordDetector,
)
from asis.voice.models import AudioData
from asis.voice.pipeline import VoicePipeline


def build_voice_parser() -> argparse.ArgumentParser:
    """Parser for ``asis voice`` (overrides config for this run only)."""
    parser = argparse.ArgumentParser(
        prog="asis voice",
        description="Run the A.S.I.S. voice subsystem (local, mock by default).",
    )
    parser.add_argument(
        "--stt-engine", default=None, help="STT engine (mock|faster-whisper)"
    )
    parser.add_argument("--stt-model", default=None, help="STT model name")
    parser.add_argument("--tts-engine", default=None, help="TTS engine (mock|pyttsx3)")
    parser.add_argument("--tts-voice", default=None, help="TTS voice")
    parser.add_argument("--tts-rate", type=int, default=None, help="TTS speaking rate")
    parser.add_argument(
        "--speaker-engine", default=None, help="speaker engine (mock|embedding)"
    )
    parser.add_argument("--wake-word", default=None, help="wake phrase")
    parser.add_argument(
        "--wake-engine", default=None, help="wake engine (mock|openwakeword)"
    )
    parser.add_argument("--wake-threshold", type=float, default=None)
    parser.add_argument("--vad-engine", default=None, help="VAD engine (mock|silero)")
    parser.add_argument("--vad-threshold", type=float, default=None)
    parser.add_argument(
        "--input-engine", default=None, help="audio input (mock|sounddevice)"
    )
    parser.add_argument(
        "--output-engine", default=None, help="audio output (mock|sounddevice)"
    )
    parser.add_argument(
        "--no-wake-word", action="store_true", help="disable wake-word gating"
    )
    parser.add_argument("--max-utterance-s", type=float, default=None)
    parser.add_argument("--silence-s", type=float, default=None)
    parser.add_argument(
        "--register-speaker",
        default=None,
        metavar="SPEAKER_ID",
        help="register a speaker from WAV sample(s) and exit (explicit only)",
    )
    parser.add_argument(
        "--sample",
        action="append",
        default=None,
        metavar="WAV",
        help="voice sample for --register-speaker (repeatable)",
    )
    parser.add_argument(
        "--list-speakers", action="store_true", help="list known speakers and exit"
    )
    parser.add_argument(
        "--provider", default=settings.ai.provider, choices=["mock", "ollama"]
    )
    parser.add_argument("--model", default=settings.ai.model)
    parser.add_argument("--memory-db", default=None, metavar="PATH")
    parser.add_argument(
        "--mode",
        default=settings.coding.default_mode,
        choices=["general", "coding", "translation"],
        help="assistant mode to use (default: %(default)s)",
    )
    parser.add_argument(
        "--workspace",
        default=None,
        metavar="PATH",
        help="coding workspace root (default: configured workspace or CWD)",
    )
    parser.add_argument(
        "--max-turns", type=int, default=0, help="stop after N turns (0=infinite)"
    )
    parser.add_argument("--debug", action="store_true")
    return parser


def _load_wav_sample(path: str) -> AudioData:
    """Load a WAV file as canonical AudioData (stdlib only, no persistence)."""
    import wave
    from pathlib import Path

    p = Path(path).expanduser()
    if not p.exists():
        raise ASISError(f"sample not found: {path}")
    with wave.open(str(p), "rb") as wf:
        n_channels = wf.getnchannels()
        sample_rate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)
        sampwidth = wf.getsampwidth()
    import struct

    fmt = {1: "b", 2: "h", 4: "i"}.get(sampwidth)
    if fmt is None:
        raise ASISError(f"unsupported sample width in {path}")
    count = n_frames * n_channels
    values = struct.unpack("<" + fmt * count, raw) if count else ()
    scale = float(2 ** (8 * sampwidth - 1))
    mono: list[float] = []
    for i in range(n_frames):
        frame = values[i * n_channels : (i + 1) * n_channels]
        mono.append(sum(float(v) / scale for v in frame) / max(1, n_channels))
    return AudioData(samples=mono, sample_rate=int(sample_rate or 16_000), channels=1)


def _build_providers(args) -> dict:
    """Build voice providers honoring CLI overrides (no global mutation)."""
    from asis.voice import factory as vf

    # STT
    if args.stt_engine is not None:
        eng = args.stt_engine.lower()
        if eng == "mock":
            stt = MockSpeechRecognizer(language=settings.voice.stt.language or None)
        elif eng in {"faster-whisper", "faster_whisper", "whisper"}:
            from asis.voice.speech.faster_whisper import FasterWhisperRecognizer

            stt = FasterWhisperRecognizer(
                model=args.stt_model or settings.voice.stt.model,
                device=settings.voice.stt.device,
                compute_type=settings.voice.stt.compute_type,
                language=settings.voice.stt.language or None,
            )
        else:
            raise ASISError(f"unsupported STT engine: {args.stt_engine}")
    else:
        stt = vf.create_speech_recognizer()

    # TTS
    if (
        args.tts_engine is not None
        or args.tts_voice is not None
        or args.tts_rate is not None
    ):
        eng = (args.tts_engine or settings.voice.tts.engine or "mock").lower()
        tts_rate = settings.voice.tts.sample_rate or settings.voice.sample_rate
        if eng == "mock":
            tts = MockTextToSpeech(sample_rate=tts_rate)
        elif eng in {"pyttsx3", "local"}:
            from asis.voice.tts.pyttsx3_engine import Pyttsx3Engine

            kwargs: dict = {
                "voice": args.tts_voice or settings.voice.tts.voice,
                "sample_rate": tts_rate,
            }
            if args.tts_rate is not None:
                kwargs["rate"] = int(args.tts_rate)
            tts = Pyttsx3Engine(**kwargs)
        else:
            raise ASISError(f"unsupported TTS engine: {args.tts_engine}")
    else:
        tts = vf.create_tts()

    # Speaker
    if args.speaker_engine is not None:
        eng = args.speaker_engine.lower()
        if eng == "mock":
            speaker = MockSpeakerIdentifier(
                confidence=settings.voice.speaker.confidence
            )
        else:
            # delegate to factory path for real engines (validates + raises helpfully)
            speaker = vf.create_speaker_identifier()
    else:
        speaker = vf.create_speaker_identifier()

    # Wake word: honor --wake-engine/--wake-word/--wake-threshold without
    # silently downgrading a configured real engine to mock.
    if args.no_wake_word:
        wake = None
    else:
        wake_engine = (args.wake_engine or settings.voice.wake.engine or "mock").lower()
        phrases = (args.wake_word or settings.voice.wake_word or "hey asis",)
        threshold = (
            float(args.wake_threshold)
            if args.wake_threshold is not None
            else float(settings.voice.wake.threshold)
        )
        if wake_engine in {"mock", "", "keyphrase", "text"}:
            wake = MockWakeWordDetector(phrases=phrases)
        elif wake_engine in {"openwakeword", "open_wake_word", "audio"}:
            from asis.voice.engines.openwakeword import OpenWakeWordDetector

            wake = OpenWakeWordDetector(
                phrases=phrases,
                threshold=threshold,
                model_path=settings.voice.wake.model or None,
            )
        else:
            try:
                wake = vf.create_wake_word_detector()
            except ASISError:
                wake = MockWakeWordDetector(phrases=phrases)

    # VAD: honor --vad-engine/--vad-threshold.
    if args.vad_engine is not None or args.vad_threshold is not None:
        eng = (args.vad_engine or settings.voice.vad.engine or "mock").lower()
        threshold = (
            float(args.vad_threshold)
            if args.vad_threshold is not None
            else float(settings.voice.vad.threshold)
        )
        if eng in {"mock", ""}:
            vad = MockVadDetector()
        elif eng in {"silero", "silero-vad", "silero_vad"}:
            from asis.voice.input.vad import SileroVadDetector

            vad = SileroVadDetector(
                sample_rate=settings.voice.sample_rate,
                threshold=threshold,
            )
        else:
            raise ASISError(f"unsupported VAD engine: {args.vad_engine}")
    else:
        try:
            vad = vf.create_vad()
        except ASISError:
            vad = MockVadDetector()

    # Audio I/O: follow configured engines (no more hardcoded mocks).
    if args.input_engine is not None:
        eng = args.input_engine.lower()
        if eng == "mock":
            audio_input = MockAudioInput([])
        elif eng in {"sounddevice", "microphone", "real"}:
            audio_input = vf.create_real_audio_input()
        else:
            raise ASISError(f"unsupported input engine: {args.input_engine}")
    else:
        try:
            audio_input = vf.create_audio_input()
        except ASISError:
            audio_input = MockAudioInput([])

    if args.output_engine is not None:
        eng = args.output_engine.lower()
        if eng == "mock":
            audio_output = MockAudioOutput()
        elif eng in {"sounddevice", "real"}:
            audio_output = vf.create_real_audio_output()
        else:
            raise ASISError(f"unsupported output engine: {args.output_engine}")
    else:
        try:
            audio_output = vf.create_audio_output()
        except ASISError:
            audio_output = MockAudioOutput()

    return {
        "audio_input": audio_input,
        "vad": vad,
        "wake_word": wake,
        "speech_recognizer": stt,
        "speaker_identifier": speaker,
        "tts": tts,
        "audio_output": audio_output,
    }


def run_voice(argv: list[str] | None = None) -> int:
    """Entry for ``asis voice``; returns process exit code."""

    logger = get_logger("voice.runtime")
    args = build_voice_parser().parse_args(argv)
    if args.debug:
        logger.info("voice debug mode on")

    # Lazy import to keep CLI import light
    from asis.app.assistant import AssistantApp
    from asis.cli.main import _provider, build_core_manager, build_memory
    from asis.system.context import RuntimeContext
    from asis.voice.input.utterance import UtteranceConfig, capture_utterance
    from asis.voice.runner import VoiceRunner, VoiceRunnerConfig

    identity = build_identity()

    # -- speaker management subcommands (explicit registration only) ------
    if args.list_speakers:
        try:
            from pathlib import Path

            from asis.voice.speaker.store import SpeakerStore

            store = SpeakerStore(Path(settings.paths.data) / "voice" / "speakers.json")
            profiles = store.list_profiles()
            if not profiles:
                print("No known speakers.")
            else:
                for p in profiles:
                    print(f"{p.speaker_id} (samples={len(p.embeddings)})")
            return 0
        except Exception as exc:
            print(f"voice startup failed: {exc}", file=sys.stderr)
            return 2
    if args.register_speaker:
        if not args.sample:
            print(
                "voice startup failed: --register-speaker needs --sample WAV",
                file=sys.stderr,
            )
            return 2
        try:
            from pathlib import Path

            from asis.voice import factory as vf
            from asis.voice.speaker.registration import register_speaker
            from asis.voice.speaker.store import SpeakerStore

            samples = [_load_wav_sample(s) for s in args.sample]
            store = SpeakerStore(
                Path(settings.paths.data) / "voice" / "speakers.json"
            )
            provider = vf.create_speaker_embedding_provider()
            profile = register_speaker(
                store, provider, args.register_speaker, samples
            )
            print(
                f"Registered '{profile.speaker_id}' "
                f"({len(profile.embeddings)} samples)."
            )
            return 0
        except ASISError as exc:
            print(f"voice startup failed: {exc}", file=sys.stderr)
            if args.debug:
                raise
            return 2
        except Exception as exc:
            print(f"voice startup failed: {exc}", file=sys.stderr)
            if args.debug:
                raise
            return 2

    try:
        engines = _build_providers(args)
    except ASISError as exc:
        print(f"voice startup failed: {exc}", file=sys.stderr)
        if args.debug:
            raise
        return 2
    except Exception as exc:  # pragma: no cover - defensive
        print(f"voice startup failed: {exc}", file=sys.stderr)
        if args.debug:
            raise
        return 2

    try:
        provider = _provider(args.provider, args.model)
    except ValueError as exc:
        print(f"voice startup failed: {exc}", file=sys.stderr)
        return 2

    event_bus = EventBus()
    interrupts = InterruptCoordinator()
    interrupts.register("voice")
    ai = AIManager(provider=provider, event_bus=event_bus)
    memory = build_memory(args.memory_db)
    # Same single CORE session as the text CLI: voice reuses the shared
    # AssistantApp path (no VoiceCoreClient). Disabled/unreachable means
    # CORE tools fail safe and spoken responses stay local.
    core_manager = build_core_manager()
    core_ctx: RuntimeContext | None = None
    if core_manager is not None:
        core_ctx = RuntimeContext()
        core_manager.start(core_ctx)
    app = AssistantApp(
        identity=identity,
        ai=ai,
        memory=memory,
        interrupts=interrupts,
        mode=args.mode,
        workspace=args.workspace,
        core=core_manager,
    )

    # Bounded utterance capture reusing the same input + VAD (no re-init).
    utterance_cfg = UtteranceConfig(
        sample_rate=settings.voice.sample_rate,
        channels=settings.voice.channels,
        block_size=settings.voice.block_size,
        max_utterance_seconds=float(
            args.max_utterance_s or settings.voice.max_utterance_s
        ),
        silence_seconds=float(args.silence_s or settings.voice.silence_s),
    )

    def _capturer(seed: AudioData) -> AudioData:
        return capture_utterance(
            engines["audio_input"],
            vad=engines["vad"],
            seed=seed,
            config=utterance_cfg,
            interrupts=interrupts,
        )

    pipeline = VoicePipeline(
        audio_input=engines["audio_input"],
        speech_recognizer=engines["speech_recognizer"],
        speaker_identifier=engines["speaker_identifier"],
        tts=engines["tts"],
        audio_output=engines["audio_output"],
        event_bus=event_bus,
        interrupts=interrupts,
        vad=engines["vad"],
        wake_word_detector=engines["wake_word"],
        utterance_capturer=_capturer if not args.no_wake_word else None,
    )

    logger.info(
        "voice startup: stt=%s tts=%s speaker=%s wake=%s in=%s out=%s",
        type(engines["speech_recognizer"]).__name__,
        type(engines["tts"]).__name__,
        type(engines["speaker_identifier"]).__name__,
        type(engines["wake_word"]).__name__ if engines["wake_word"] else "disabled",
        type(engines["audio_input"]).__name__,
        type(engines["audio_output"]).__name__,
    )

    runner = VoiceRunner(
        pipeline,
        app=app,
        config=VoiceRunnerConfig(
            require_wake_word=not args.no_wake_word,
            max_turns=int(args.max_turns or 0),
            shutdown_phrase=settings.identity.shutdown_phrase,
        ),
        on_response=lambda response, _result: print(response),
        on_error=lambda exc: print(f"voice error: {exc}", file=sys.stderr),
    )

    ctx = RuntimeContext()
    try:
        runner.start(ctx)
    except Exception as exc:
        print(f"voice startup failed: {exc}", file=sys.stderr)
        if args.debug:
            raise
        return 2

    print(identity.greeting)
    if isinstance(engines["audio_input"], MockAudioInput):
        label = "mock audio"
    else:
        label = "live audio"
    print(f"Voice mode running ({label}). Say the shutdown phrase to exit.")
    try:
        summary = runner.run()
    except KeyboardInterrupt:
        print("\nShutting down.")
        summary = {"reason": "keyboard-interrupt"}
    finally:
        with contextlib.suppress(Exception):
            runner.stop(ctx)
        if core_manager is not None and core_ctx is not None:
            with contextlib.suppress(Exception):
                core_manager.stop(core_ctx)
        reason = summary.get("reason") if isinstance(summary, dict) else "?"
        logger.info("voice shutdown complete (%s)", reason)
    if args.debug and isinstance(summary, dict):
        logger.info("voice summary: %s", summary)
    return 0


# Backwards-compat helper for tests: run one turn with scripted mocks.
def run_voice_once(
    segments: list[AudioData],
    transcript: str = "hello",
    require_wake_word: bool = False,
) -> dict:
    """Run a single pipeline turn with scripted mocks (no hardware)."""
    pipeline = VoicePipeline(
        audio_input=MockAudioInput(segments),
        speech_recognizer=MockSpeechRecognizer(text=transcript),
        speaker_identifier=MockSpeakerIdentifier(),
        tts=MockTextToSpeech(),
        audio_output=MockAudioOutput(),
        vad=MockVadDetector(),
        wake_word_detector=MockWakeWordDetector() if require_wake_word else None,
    )
    return pipeline.run_once(require_wake_word=require_wake_word)
