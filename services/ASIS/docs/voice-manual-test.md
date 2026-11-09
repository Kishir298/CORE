# Voice Manual Hardware Test (not CI)

> [!CAUTION] Status: **NOT PERFORMED** — do not claim validation until
> each step below passes on hardware (check every box as you go).

Perform on a real Mac/Windows machine with microphone + speakers.
Do not claim validation until each step passes on hardware.

## 1. Install voice extras

```bash
pip install -r requirements/voice.txt
```

- [ ] Install completes with no errors.

## 2. Models

- STT: Faster-Whisper `small` auto-downloads on first use (CPU `int8`).
- VAD: Silero auto-loads (`silero-vad` + `torch` CPU).
- Wake: openWakeWord default model or `ASIS_VOICE_WAKE_MODEL=/path/to/model.onnx`.
- Speaker: SpeechBrain `speechbrain/spkrec-ecapa-voxceleb` auto-downloads.

- [ ] Each required model is present (no `MODEL_NOT_INSTALLED` at startup).

## 3. Configure `.env`

```bash
ASIS_VOICE_INPUT_ENGINE=sounddevice
ASIS_VOICE_OUTPUT_ENGINE=sounddevice
ASIS_VOICE_VAD_ENGINE=silero
ASIS_VOICE_WAKE_ENGINE=openwakeword
ASIS_VOICE_STT_ENGINE=faster-whisper
ASIS_VOICE_SPEAKER_ENGINE=embedding
ASIS_VOICE_TTS_ENGINE=pyttsx3
```

- [ ] Settings load with no `ConfigurationError`.

## 4. Select microphone/speaker

- List devices via OS settings; set `device` in code if non-default
  (`create_real_audio_input(device=N)`).
- Start with quiet room, normal speaking volume.

- [ ] Correct microphone/speaker selected.

## 5. Start A.S.I.S.

```bash
asis voice --mode general --debug
```

Expect greeting + `Voice mode running (live audio)`.

- [ ] Voice mode starts and greets.

## 6. Wake word

Say `hey asis …`. Only wake phrases should trigger STT; ambient speech
should return to waiting without a response.

- [ ] Wake word triggers; ambient speech does not.

## 7. Command + STT

Say `hey asis what time is it`. Verify transcription leads to a spoken
+ printed answer.

- [ ] Correct transcription → correct spoken + printed answer.

## 8. A.S.I.S. response + TTS

Verify audible response, no temp files left (`/tmp/asis-tts-*` cleaned).

- [ ] Audible response; temp files cleaned.

## 9. Interruption

Press `Ctrl-C` mid-response or cancel `voice` scope; verify prompt
returns and `voice.interrupted` is emitted (with `--debug` logs).

- [ ] Interruption returns to prompt with `voice.interrupted` logged.

## 10. Speaker recognition

```bash
asis voice --register-speaker alice --sample alice1.wav --sample alice2.wav
asis voice --list-speakers
```

Speak as alice vs stranger; verify known/unknown in logs, and that
strangers are never auto-registered.

- [ ] Known speaker recognized; strangers never auto-registered.

## 11. Coding mode through voice

Say `switch to coding mode`, then `hey asis list files here` (or
`read file X`). Verify A.S.C.S. tools/context apply, same model as text
(no second provider). Say `switch to general mode` to return.

- [ ] Coding mode works through voice with the same model.

## 12. Clean shutdown

Say `asis shutdown`; verify `Shutting down.` is spoken, streams closed,
process exits `0` within `ASIS_SHUTDOWN_TIMEOUT`.

- [ ] Clean shutdown: spoken confirmation, exit code `0` in time.
