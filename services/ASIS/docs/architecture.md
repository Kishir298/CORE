# A.S.I.S. Architecture

A.S.I.S. (**A Smart Intelligence System**) is the intelligence/assistant
layer of the R.I.S.A.R.M.S. ecosystem. It runs independently: AI
interaction, conversation, memory, tools, permissions, voice, and
identity all work with no C.O.R.E. or R.E.S.C.S. process present (C.O.R.E.
is a real but optional uplink; R.E.S.C.S. remains a future boundary —
see `docs/integration.md`).

A.S.I.S. is offline-first: everything above runs with no public
internet — the only intentional internet boundary is the web tool
branch (`web_search`/`web_fetch`, optional via `ASIS_WEB_ENABLED`),
and CORE stays LAN-only. Details in `docs/offline.md`.

## Runtime shape

```text
User
 │
 ▼
CLI / Voice Interface          asis/cli/main.py, asis/cli/voice.py
 │
 ▼
Conversation Engine            asis/ai/conversation.py (bounded session)
 │
 ├── Context Manager           asis/ai/context.py (system prompt + limits)
 │
 ├── Memory                    asis/memory/ (local SQLite, see docs/ai-memory.md)
 │
 ├── Model Provider            asis/ai/ (Ollama default, mock for tests/dev)
 │
  └── Tool System               asis/tools/ (registry → router → executor)
        │  Permission Manager     asis/permissions/ (levels + confirmation)
        │  Tool Execution         bounded by tools.timeout
        │
        ├── CORE tools → CORE adapter → CORE-CLIENT → CORE-HOST (optional)
        │
        └── Web tools → WebProvider → Internet (optional, bounded)
```

**Runtime wiring status:** the CLI and voice paths share one stateful
`AssistantApp` (`asis/app/assistant.py`) owning a single
`ConversationSession` per session: input → deterministic orchestration
(`asis/ai/orchestrator.py`: intent, memory/doc/tool needs, constraints)
→ query-scoped memory retrieval → labeled bounded `ContextAssembler`
(`SYSTEM`/`MODE`/`CAPABILITIES`/memory/docs) → `InferenceEngine`
(`generate` or true-streaming `generate_streamed`, qwen3 thinking
stripped to metadata, per-turn cancel reset) → `AIManager` →
optional tool actions (router → permission → executor, up to ASIS_TOOL_MAX_CALLS_PER_TURN validated native calls + final generation) → final
response stored back in the session, streamed live to the terminal. Memory is recalled via
`MemoryManager.search_context()` (fail-open: log + continue when
retrieval fails). Normal conversation never requires a tool.

**Modes:** `AssistantApp` carries `app.mode` (`GENERAL`/`CODING`/
`TRANSLATION`, `asis/app/modes.py`); CODING is A.S.C.S. — same
provider/model instance, plus mode instructions (`asis/app/profiles.py`), a bounded
`REPOSITORY CONTEXT` block (`asis/coding/context.py`) and the
workspace-bound coding tool registry (`asis/coding/tools.py`).
Switching modes never recreates the provider. See `docs/coding.md`.

## Voice pipeline

```text
Microphone
    ↓
Audio Input                    asis/voice/input/ (mock default, sounddevice real)
    ↓
Wake Word / VAD                engines + input/vad.py (mock default)
    ↓
Speech Recognition             speech/ (mock default, faster-whisper real)
    ↓
Speaker Identification         speaker/ (mock default, embedding real)
    ↓
A.S.I.S. Processing            shared AssistantApp (session + memory + tools)
    ↓
Response
    ↓
Text-to-Speech                 tts/ (mock default, pyttsx3 real)
    ↓
Audio Output                   output/ (mock default, sounddevice real)
```

Every stage is mock-by-default and independently testable; real
engines are explicit opt-ins via `ASIS_VOICE_*_ENGINE`. Details in
`docs/voice.md`.

## Lifecycle / shutdown

`asis/system/lifecycle.py` starts components in registration order and
stops them in reverse; per-component stop failures are logged, not
re-raised, and startup failure stops already-started components.
`ASISRuntime` (`asis/system/runtime.py`) tracks
`CREATED → STARTING → RUNNING → STOPPING → STOPPED/FAILED` and cancels
all interrupt scopes on stop. `stop()` enforces
`settings.runtime.shutdown_timeout` with a bounded join: on expiry it
logs the stuck components, transitions to FAILED and raises
`TimeoutError` instead of hanging. Shutdown is triggered by the configured
phrase (default `asis shutdown`) in the CLI/voice REPLs, by
`--max-turns`, or by `Ctrl+C`; the voice loop always runs
`pipeline.stop()` in `finally`.

`InterruptCoordinator` (`asis/system/interrupt.py`, scopes
`inference` and `voice`) lets one subsystem cancel another's blocking
work via `CancellationError`.

## Boot / Ollama lifecycle

`asis` runs a blocking boot sequence (`asis/app/boot.py`) before any
prompt: configuration → identity → personality → memory → tools →
Ollama reachable → silent model readiness probe (`hello` sent directly
through the existing provider instance — single USER message, no
session/context/tools/memory, `think=False`, small `num_predict`) →
`A.S.I.S.` header + status bar. The probe text and reply are never printed
or persisted; failure prints `[FAIL]` and exits without entering
interactive mode. ESC cancels the in-flight turn once interactive;
`CTRL+C`/exit/EOF/failure runs centralized cleanup in `entry()`.

Ollama servers are ownership-safe (`asis/ai/ollama_lifecycle.py`):
already-running servers are external (`owned=False`) and never stopped;
only a process actually started by A.S.I.S. (`ASIS_OLLAMA_MANAGED=auto/on`,
default `auto`) is owned and terminated on every exit path with a bounded
graceful-then-force stop (`ASIS_OLLAMA_SHUTDOWN_TIMEOUT`, default 10s).
No kill-by-name (`taskkill`/`pkill`) exists anywhere.

Known scope limits: the `voice`/`translate`/`calculate` subcommand
runners predate this lifecycle and still manage their own startup
(main `asis` REPL + `--message` are covered); ESC cancels turns once
interactive — during the synchronous boot probe use `CTRL+C` (bounded
by the provider timeout, owned Ollama still cleaned up).

## Identity

`asis/identity/`: frozen `Identity(name, title, personality,
preferences, greeting)` rendered from `settings.identity`
(`build_identity()`), so renaming A.S.I.S. is configuration, not code.
Default personality template supports `{name}`/`{title}`.

## Package map

```text
asis/
├── ai/               inference, conversation, context, providers
├── app/              assistant runtime, tool actions, auto-memory, result (modes GENERAL/CODING/TRANSLATION)
├── calculator/       offline math engine (SymPy-backed, verified)
├── cli/              entry point, chat REPL, voice loop (python -m asis alias supported)
├── coding/           A.S.C.S. mode profiles, workspace context, coding tools
├── configuration/    defaults → env → validated Settings
├── documents/        document store, parsers, context injection
├── errors/           ASISError hierarchy (see below)
├── events/           EventBus (AI, tools, memory, voice events)
├── identity/         config-driven identity + personality
├── integrations/     real CORE adapter + mock; RESCS contract (future)
├── logging/          console + rotating-file handlers
├── memory/           local SQLite memory
├── permissions/      levels, confirmation, sandbox, secrets helper
├── system/           lifecycle, runtime, interrupts
├── tools/            registry, router, executor, provided tools
├── translation/      offline translation engine (registry, detection, providers)
├── web/              web provider (search + fetch), SSRF guard, extraction
└── voice/            canonical voice subsystem
```

Entry: installed `asis` command; `python -m asis` alias supported via `asis/__main__.py`.

## Error hierarchy

`asis/errors/`: `ASISError` → `ConfigurationError`, `ModelError` →
`InferenceError`, `ConversationError`, `ToolError` →
`ToolValidationError`/`ToolNotFoundError`, `PermissionError`
(intentionally shadows the builtin), `VoiceError` →
`SpeechRecognitionError`/`SpeakerRecognitionError`/`TTSError`,
`MemoryError`, `CancellationError`. Failures surface as typed
exceptions; the CLI prints them (exit `2` for voice startup failures
unless `--debug` re-raises).

## Logging

`asis/logging/`: level from `settings.runtime.log_level` (unknown →
`INFO`), `get_logger(name)` returns `asis` children with
`propagate=False`; console `StreamHandler` + `RotatingFileHandler`
(`logs/asis.log`, 5 MB × 5, UTF-8), format
`[asctime] [level] [name] message`. No redaction mechanism exists —
**never log secrets** (policy; see `docs/cli-testing.md` security
notes and `.env.example`).
