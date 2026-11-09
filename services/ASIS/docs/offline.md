# Offline-First Operation

A.S.I.S. runs locally without public internet. Startup, conversation,
memory, local tools, A.S.C.S. coding mode, voice (mock or locally
installed engines), and native function calling all work with Wi-Fi off
and DNS unavailable.

## What is local

| Capability | Implementation | Network |
|---|---|---|
| LLM inference | Ollama on loopback (`ASIS_AI_ENDPOINT`, default `http://127.0.0.1:11434`) or `mock` | None / loopback |
| Memory | Local SQLite (`ASIS_MEMORY_*`, `local` only) | None |
| Local tools | `echo`, `current_time`, `calculate` | None |
| Coding (A.S.C.S.) | Workspace FS + local `git`/`pytest`/`python` | None |
| Voice mocks | All `ASIS_VOICE_*_ENGINE=mock` (defaults) | None |
| Voice real engines | faster-whisper / speechbrain / silero / openwakeword / pyttsx3 / sounddevice | None **after** one-time model setup (below) |
| CORE uplink | CORE-CLIENT ↔ CORE-HOST over LAN/TLS, disabled by default | LAN only, optional |

## Exceptions (need internet)

Only explicitly invoked web tools: `web_search` / `web_fetch`
(`asis/web/`, gated by `ASIS_WEB_ENABLED`, SSRF-guarded). Offline they
fail with `WEB_UNAVAILABLE`/`WEB_DISABLED` while everything else keeps
working — see `docs/tools-permissions.md`. There is no global
internet-required switch; the default state is local-first.

## Models must be installed before offline runtime

Runtime never downloads models automatically. A missing model is a
deterministic error, never a silent download:

- **Ollama:** install Ollama and pull the configured model while online
  (`ollama pull qwen3:14b` for the default `ASIS_AI_MODEL`), then run
  offline. Down server → `InferenceError("Could not communicate with
  Ollama: …")`. Without Ollama at all, run fully offline with
  `ASIS_AI_PROVIDER=mock`.
- **Voice weights:** real engines fetch weights once via their upstream
  library on first use (HuggingFace/torch hub caches). Pre-cache while
  online: install voice extras (`pip install -r requirements/voice.txt`)
  and run each configured engine once with internet access
  (STT `ASIS_VOICE_STT_MODEL`, speaker `ASIS_VOICE_SPEAKER_MODEL`,
  Silero VAD default, OpenWakeWord default or a local file via
  `ASIS_VOICE_WAKE_MODEL`). Afterwards they run offline. If weights are
  absent, constructors raise `MODEL_NOT_INSTALLED` naming the engine,
  the model, and the `…=mock` fallback — no retry loop, no download.

Never commit model weights to Git.

## Translation

The offline Translation Engine (`asis/translation/`, see
`docs/translation.md`) runs locally under the same rules: local models
(MADLAD-400 3B MT via transformers/torch, or mock backend),
`TRANSLATION_MODEL_NOT_INSTALLED` when weights are absent, no cloud API.
Only `translate_text` and TRANSLATION mode need the local model file;
everything else about translation (registry, detection, cache, tools)
works with zero dependencies.

## Offline test mode

`tests/test_offline.py` simulates no-internet deterministically (public
DNS fails, loopback keeps real semantics; no machine networking is
touched) and proves startup, conversation, memory, tools, coding,
voice, CORE-disabled mode, native calling, web isolation, and the
no-hidden-network guard (only `ai/providers/ollama.py` and
`web/provider.py` may use `requests`; only `web/security.py` may use
`sockets`). Live web checks stay opt-in (`ASIS_WEB_LIVE=1`).

## Validation status

Offline behavior is validated via the simulated suite above, which
passes in CI-like conditions. A physical Wi-Fi-off run on target
hardware: NOT PERFORMED — do not claim it until physically done.
