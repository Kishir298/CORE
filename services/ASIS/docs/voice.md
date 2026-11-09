# Voice (`asis/voice/`)

Canonical and only voice implementation (the old `02_voice` tree was
removed). Status labels: **Implemented** = works today, **Mock** =
scripted test double, **Optional** = needs an extra + hardware/model.

## Pipeline order (`VoicePipeline.run_once`)

Audio-first gating (no ambient speech sent to STT unnecessarily):

`listen → check_voice_activity (voice.vad) → detect_wake_word(audio)
→ capture_command (utterance, bounded) → transcribe → normalize_text →
detect_wake_text confirmation (if required) → identify_speaker →
process_fn (voice.assistant.started/finished) → speak`, returning
`{text, speaker, response, status}` with status
`spoken | no-speech | no-wake-word`. An audio-gate miss returns
`no-wake-word` with empty text and zero STT calls. Each stage is
independently callable and interrupt-checked (`voice.interrupted` on
cancel); `VoiceEvent`s never carry raw audio or embeddings.

Continuous listening lives in `VoiceRunner` (`asis/voice/runner.py`,
`RuntimeComponent name="voice"`): waiting → wake → command → response
→ waiting, with `max_turns`, shutdown-phrase, idle sleep (no 100% CPU
spin), single provider set reused across turns, and bounded shutdown
via `InterruptCoordinator("voice")` + `pipeline.stop()`.

## Engines

| Stage | Mock (default) | Real (opt-in) | Engine names |
|---|---|---|---|
| Audio input | `MockAudioInput` | `SoundDeviceInputProvider` (Optional) | `mock`, `sounddevice`, `microphone`, `real` |
| Audio output | `MockAudioOutput` | `SoundDeviceOutputProvider` (Optional) | `mock`, `sounddevice`, `real` |
| VAD | `MockVadDetector` | `SileroVadDetector` (Optional, torch+silero) | `mock`, `silero*` |
| Wake word | `MockWakeWordDetector`, `KeyphraseWakeWordDetector` | `OpenWakeWordDetector` (Optional) | `mock`, `keyphrase`, `openwakeword`, … |
| STT | `MockSpeechRecognizer` | `FasterWhisperRecognizer` (Optional) | `mock`, `faster-whisper`, … |
| Speaker ID | `MockSpeakerIdentifier` | `EmbeddingSpeakerIdentifier` (Optional, speechbrain) | `mock`, `embedding`, … |
| TTS | `MockTextToSpeech` | `Pyttsx3Engine` (Optional, offline wav) | `mock`, `pyttsx3`, `local` |

Unknown engine names raise `VoiceError` pointing at the corresponding
`ASIS_VOICE_*_ENGINE` variable. All `*_ENGINE` defaults are `mock`.

## Details

- **Audio input** (`input/`): `Microphone` (lazy sounddevice,
  discovery/capture), `AudioBuffer` (thread-safe deque, numpy-optional),
  `utterance.py` (`capture_utterance` + `UtteranceConfig`: VAD-gated
  end-of-utterance, `ASIS_VOICE_MAX_UTTERANCE_S`/`ASIS_VOICE_SILENCE_S`
  bounds, fail-open to the wake segment),
  `VoiceActivityDetector` (256/512 frames) + `SileroVadDetector` adapter.
- **STT** (`speech/`): `SpeechTranscriber` (lazy WhisperModel,
  auto-language) + `FasterWhisperRecognizer` adapter
  (`model/device/compute_type/language` from settings) +
  `TranscriptionNormalizer`.
- **Speaker** (`speaker/`): JSON-file/memory `SpeakerStore` (never
  stores audio), `register_speaker()` merge (explicit CLI only:
  `asis voice --register-speaker ID --sample a.wav`, `--list-speakers`;
  never auto-registers strangers), `EmbeddingSpeakerIdentifier`
  (`threshold`, `cosine` metric, `unknown` fallback), pure-python
  embedding math + lazy SpeechBrain provider. Known speakers prefix
  chat as `[id] text` for memory context; no separate voice memory.
- **TTS** (`tts/`): `Pyttsx3Engine` renders offline to wav and returns
  `AudioData` (temp files always cleaned); empty `voice` allowed,
  `--tts-rate` override supported.
- **Output** (`output/`): `SoundDeviceOutputProvider.play/stop` with
  validation and channel-mismatch warning.
- **Wake** (`engines/`): text keyphrase detector (fallback/test only),
  scriptable mocks, `OpenWakeWordDetector` (threshold + optional model
  path, `ASIS_VOICE_WAKE_THRESHOLD`/`ASIS_VOICE_WAKE_MODEL`).
- **Modes** (`commands.py` + `runner.py`): explicit phrases only
  (`switch to coding/general/translation mode`, `enable ascs`, …) flip
  `AssistantApp.set_mode()` without touching provider/model; anything
  else flows to `app.chat()`. Same provider/model/session/memory/tools
  as text; A.S.C.S. coding tools/context apply when CODING is active.
  In TRANSLATION mode transcripts are translated via the shared
  Translation Engine and may be spoken back (see `docs/translation.md`).
   Spoken `core:…` commands execute CORE tools through the same
   Router/permission path as typed `core:…` commands; CORE failure
   becomes a spoken-safe notice, never a traceback. Native function
   calls work identically over voice: transcripts flow through
   `app.chat()`, so the model may invoke tools natively before the
   final response is spoken — no voice-specific tool execution,
   networking, or permissions exist.

## CLI (`asis voice`)

Follows configured `ASIS_VOICE_*_ENGINE` values (no hardcoded mocks).
Overrides: `--input-engine/--output-engine/--vad-engine/--wake-engine`,
`--wake-word/--wake-threshold/--vad-threshold`, `--stt-engine/--stt-model`,
`--tts-engine/--tts-voice/--tts-rate`, `--speaker-engine`,
`--max-utterance-s/--silence-s`, `--no-wake-word`, `--mode/--workspace`,
`--max-turns`, `--debug`. Failures are structured exit `2`, never raw
tracebacks unless `--debug`.

## Status labels

- **IMPLEMENTED**: pipeline audio gating, utterance capture, runner loop,
  factory + CLI wiring, speaker store/registration, mode commands,
  interruption (`voice` scope), lifecycle `stop()`, events
  (`voice.vad/assistant.started/finished/interrupted` added).
- **TESTED WITH MOCKS**: `tests/test_voice.py`, `test_voice_audio_gate.py`
  (no hardware).
- **OPTIONAL REAL-PROVIDER TEST**: `tests/test_voice_real.py`
  (`ASIS_REAL_VOICE_TESTS=1`, skips when deps missing).
- **MANUAL HARDWARE VALIDATION**: see `docs/voice-manual-test.md` (not
  claimed until performed on real Mac/Windows hardware).

Voice uses the same `AssistantApp` intelligence as the text CLI
(stateful session + memory recall + single tool cycle via
`process_fn`), not a second AI implementation.
