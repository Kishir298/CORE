# Offline Translation Engine

A.S.I.S.-owned local translation subsystem: provider abstraction,
language registry, model management, routing, caching, offline
detection, tool interface, voice integration, and safety controls.
Runtime never requires internet and never downloads models.

## Model selection

**Default backend: MADLAD-400 3B MT** (`google/madlad400-3b-mt`) via
transformers + torch on CPU.

| Candidate | License | Verdict |
|---|---|---|
| MADLAD-400 3B MT | Apache-2.0, 450+ languages, single T5 model | ✅ default — compatible with this project's MIT license |
| NLLB-200 distilled 600M | CC-BY-NC-4.0 (non-commercial, research-only, not for production) | ❌ rejected — conflicts with MIT-licensed distribution; provider seam allows it later for non-commercial forks |
| Opus-MT pair models | CC-BY-4.0 permissive, fast on CPU | Future provider option (one model per pair — poor fit for 100+ default) |
| SeamlessM4T | CC-BY-NC-4.0 | ❌ same license problem as NLLB |

Licenses verified September 2026 against HuggingFace model cards; always
re-confirm the current license text before deployment. Model weights are
never committed — the user obtains them while online (see Installation).

## Architecture

```text
User
 │
 ▼
A.S.I.S. (GENERAL / CODING / TRANSLATION / Voice — one AssistantApp)
 │
 ├── translate_text tool → ToolRegistry → PermissionManager (LOW) → ToolExecutor
 │        └── TranslationEngine → TranslationProvider → Local model
 │
 └── TRANSLATION mode → direct deterministic translation (no LLM needed)
```

- `asis/translation/provider.py` — `TranslationProvider` ABC
  (`translate`, `name`, `model_id`); `MadladProvider` (lazy
  transformers/torch, `local_files_only`, greedy decode, 512-token
  input cap); `MockTranslationProvider` (scripted pairs for tests).
- `asis/translation/languages.py` — **136-language registry** (`code`,
  `name`, `native_name`, `script`, text/speech-input/speech-output
  flags), authoritative for engine, detection, tools, CLI, voice,
  validation. MADLAD `<2xx>` control tags via `madlad_tag`.
- `asis/translation/detection.py` — dependency-free script +
  stopword detector; uncertain input returns `uncertain=True` instead
  of an invented language.
- `asis/translation/engine.py` — `translate_text()` / `detect_language()`
  / `supported_languages()` / `is_language_supported()`; span protection
  (URLs, emails, paths, backtick code survive verbatim); same-language
  passthrough; structured `TranslationResult`.
- `asis/translation/cache.py` — bounded in-memory LRU (configurable).
- `asis/translation/voice.py` — STT→translate→TTS bridge reusing the
  existing voice abstractions.
- `asis/tools/provided/translation_tools.py` — `translate_text`
  (`text`, `target_language`, optional `source_language` → auto-detect).

## Language coverage (honest split)

- **136 text translation languages** (registry; MADLAD-400 covers 450+,
  registry curates the subset A.S.I.S. exposes).
- **Speech input**: subset flagged `supported_for_speech_input`
  (faster-whisper auto-detects language; STT language flows into
  translation or falls back to detection).
- **Speech output**: subset flagged `supported_for_speech_output`
  (host OS must provide a matching pyttsx3 voice; otherwise
  `TTS_LANGUAGE_UNSUPPORTED`). Text→text never implies speech→speech.

## Installation (while online)

```bash
pip install transformers torch   # inference backend (CPU)
# Fetch weights once into a local directory, e.g.:
# huggingface-cli download google/madlad400-3b-mt --local-dir ~/.asis-models/madlad400-3b-mt
```

Then point A.S.I.S. at it:

```text
ASIS_TRANSLATION_PROVIDER=madlad
ASIS_TRANSLATION_MODEL_PATH=~/.asis-models/madlad400-3b-mt
ASIS_TRANSLATION_DEVICE=cpu
```

Without weights or libraries: deterministic
`TRANSLATION_MODEL_NOT_INSTALLED` (or `ASIS_TRANSLATION_PROVIDER=mock`
for tests/dev). Expect 3B-model CPU latency (tens of seconds per
request on constrained hardware); keep inputs short, leave the cache on.

## Configuration

`ASIS_TRANSLATION_ENABLED/PROVIDER/MODEL/MODEL_PATH/DEVICE/CACHE_ENABLED/CACHE_SIZE/DEFAULT_SOURCE/DEFAULT_TARGET/MAX_CHARS`
(see `docs/configuration.md`, `.env.example`). Invalid values raise
`ConfigurationError`; disabled tools return `TRANSLATION_DISABLED`.

## Offline guarantees

No internet, DNS, HTTP, API keys, or cloud services at runtime (the
hidden-network guard test enforces the import surface). Missing model +
offline still yields the deterministic install error. Live model checks
are opt-in (`ASIS_TRANSLATION_LIVE=1`,
`tests/test_translation_live.py`).

## Usage

```bash
asis translate --to fr --message "Hello"        # single-shot
asis translate --to hi                          # REPL (/tr-to, /tr-from, /mode)
asis --mode translation --message "..."         # chat CLI in translation mode
```

Voice: `enable translation mode` → speak → STT → detect → translate →
text reply, or TTS speaks the translation (speech→speech / text→speech).

## Errors

`TRANSLATION_DISABLED`, `TRANSLATION_MODEL_NOT_INSTALLED`,
`TRANSLATION_UNSUPPORTED_LANGUAGE`, `TRANSLATION_PROVIDER_ERROR`,
`TRANSLATION_INVALID_INPUT`, `TRANSLATION_TOO_LARGE`,
`LANGUAGE_DETECTION_FAILED`, `TTS_LANGUAGE_UNSUPPORTED`,
`STT_LANGUAGE_UNSUPPORTED` — all sanitized. Translated text is data:
`"delete all my files"` in any language stays text, never an action.

## Known limitations

- 3B CPU inference is slow; no streaming; 512-token input cap.
- In-repo detection covers major languages well; rare/short input
  returns uncertainty — specify the source explicitly.
- TTS language reach depends on host OS voices.
- Live MADLAD validation: NOT PERFORMED (no weights on this machine) —
  do not claim it until run. Gate checklist: `config.json` +
  `tokenizer.json` + `*.safetensors`/`*.bin` under
  `ASIS_TRANSLATION_MODEL_PATH`, `transformers` + `torch` installed, then
  `ASIS_TRANSLATION_LIVE=1 ASIS_TRANSLATION_MODEL_PATH=<dir> python -m pytest tests/test_translation_live.py -q`
  (without weights the suite now skips with a clear reason instead of failing).
