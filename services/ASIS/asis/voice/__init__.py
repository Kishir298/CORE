"""
A.S.I.S. voice subsystem.

Engines are pluggable; the default configuration uses mock engines so
A.S.I.S. runs without audio hardware or heavy AI dependencies.
"""

from .commands import parse_voice_mode_command
from .engines import (
    KeyphraseWakeWordDetector,
    MockAudioInput,
    MockAudioOutput,
    MockSpeakerEmbeddingProvider,
    MockSpeakerIdentifier,
    MockSpeechRecognizer,
    MockTextToSpeech,
    MockVadDetector,
    MockWakeWordDetector,
)
from .factory import (
    create_audio_input,
    create_audio_output,
    create_speaker_identifier,
    create_speech_recognizer,
    create_tts,
    create_voice_engines,
)
from .input.utterance import UtteranceConfig, capture_utterance
from .models import AudioData, SpeakerResult, TranscriptionResult, VoiceEvent
from .pipeline import VoicePipeline
from .providers import (
    AudioInputProvider,
    AudioOutputProvider,
    SpeakerEmbeddingProvider,
    SpeakerIdentifier,
    SpeechRecognizer,
    TextToSpeechProvider,
    VadDetector,
    WakeWordDetector,
)
from .runner import VoiceRunner, VoiceRunnerConfig

__all__ = [
    "AudioData",
    "AudioInputProvider",
    "AudioOutputProvider",
    "KeyphraseWakeWordDetector",
    "MockAudioInput",
    "MockAudioOutput",
    "MockSpeakerEmbeddingProvider",
    "MockSpeakerIdentifier",
    "MockSpeechRecognizer",
    "MockTextToSpeech",
    "MockVadDetector",
    "MockWakeWordDetector",
    "SpeakerEmbeddingProvider",
    "SpeakerIdentifier",
    "SpeakerResult",
    "SpeechRecognizer",
    "TextToSpeechProvider",
    "TranscriptionResult",
    "UtteranceConfig",
    "VadDetector",
    "VoiceEvent",
    "VoicePipeline",
    "VoiceRunner",
    "VoiceRunnerConfig",
    "WakeWordDetector",
    "capture_utterance",
    "create_audio_input",
    "create_audio_output",
    "create_speaker_identifier",
    "create_speech_recognizer",
    "create_tts",
    "create_voice_engines",
    "parse_voice_mode_command",
]
