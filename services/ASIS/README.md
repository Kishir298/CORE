# A.S.I.S. — A Smart Intelligence System

Intelligence/assistant layer of the R.I.S.A.R.M.S. ecosystem. Runs
independently — no C.O.R.E. or R.E.S.C.S. required (C.O.R.E. is a real
but optional uplink; R.E.S.C.S. remains a future boundary; see
`docs/integration.md`).

## Status

| Area | Status |
|---|---|
| Repository structure | Implemented |
| Configuration + validation | Implemented |
| AI provider abstraction | Implemented |
| Ollama provider | Implemented (optional dep) |
| Conversation / context | Implemented + wired (`AssistantApp` owns session) |
| Intelligence orchestration (deterministic intent + true streaming) | Implemented + tested (rule-based `orchestrator`, thinking stripped to metadata, ESC-safe turn reset; live single-turn + name recall PASS with `qwen3:14b`) |
| Local memory (SQLite) | Implemented + wired (query-scoped recall, fail-open) |
| Tools (`echo`, `current_time`) | Implemented + application-wired (native function calling primary, heuristic fallback, permission-mandatory) |
| Web access (`web_search`, `web_fetch`) | Implemented + application-wired (shared registry for GENERAL/A.S.C.S./voice, SSRF-guarded bounded provider, optional via `ASIS_WEB_ENABLED`) |
| Translation (`translate_text`, TRANSLATION mode) | Implemented, offline-first (136 text languages, MADLAD-400 backend optional, mock by default; see `docs/translation.md`) |
| Calculator (`calculate`, 30 operations) | Implemented, offline-first (SymPy-backed exact math + verification; see `docs/calculator.md`) |
| A.S.C.S. coding mode | Implemented + wired (shared provider/model, workspace-bound tools) |
| Permissions / confirmation | Implemented (no ungated dangerous tools; HIGH/CRITICAL gated) |
| Voice architecture + mocks | Implemented |
| Local STT / TTS / speaker / wake / VAD | Implemented (pipeline+mocks; optional deps; hardware NOT PERFORMED) |
| CLI (`asis`, `asis voice`) | Implemented (stateful multi-turn) |
| CLI reference design | Implemented (status panel, arrow bubbles, tool badges, attachment chips, composer; see `CLI.jpeg`) |
| Multi-person identity + WhatsApp persona | Implemented (analysis, timeline, calibration, `/persona <name>` simulation, `/identity answer`) |
| Shutdown timeout | Implemented (bounded stop, FAILED + log on expiry) |
| C.O.R.E. integration | Implemented (optional uplink; standalone by default; LAN NOT PERFORMED) |
| Offline-first | Implemented (simulated suite passes; physical Wi-Fi-off NOT PERFORMED; see `docs/offline.md`) |
| R.E.S.C.S. integration | Future (placeholder adapter) |

## Docs

| File | Covers |
|---|---|
| `docs/architecture.md` | runtime, lifecycle, identity, errors, logging |
| `docs/calculator.md` | offline calculator engine, operations, syntax, limits |
| `docs/translation.md` | offline translation engine, languages, model, config |
| `docs/offline.md` | offline-first operation, model setup, web boundary |
| `docs/configuration.md` | settings, precedence, validation, paths |
| `docs/ai-memory.md` | providers, inference, conversation, memory |
| `docs/coding.md` | A.S.C.S. modes, workspace, coding tools, permissions |
| `docs/tools-permissions.md` | tools, permissions, sandbox, secrets |
| `docs/voice.md` | pipeline, engines, mock-vs-real matrix |
| `docs/voice-manual-test.md` | manual voice hardware checklist (NOT PERFORMED) |
| `docs/cli-testing.md` | CLI flags, tests, dependencies, workflow |
| `docs/integration.md` | C.O.R.E. (real adapter) / R.E.S.C.S. future boundary |

## Layout

```text
ASIS/
├── asis/                  # sole production package
│   ├── ai/                # inference, conversation, context engines
│   ├── app/               # application orchestration
│   ├── cli/               # `asis` entry point + voice loop
│   ├── configuration/     # centralized settings
│   ├── documents/         # document store, parsers, context injection
│   ├── identities/        # identity analysis / matching / timeline
│   ├── integrations/      # C.O.R.E. adapter (real) / R.E.S.C.S. (future)
│   ├── memory/            # local memory provider
│   ├── storage/           # storage domains + migration
│   ├── tools/             # tool system + permissions
│   ├── calculator/       # offline calculator engine (SymPy-backed, verified)
│   ├── translation/      # offline translation engine (registry, detection, providers)
│   ├── web/              # web provider (search + fetch, SSRF guard)
│   ├── voice/             # sole production voice implementation
│   └── ...                # full map: `docs/architecture.md`
├── tests/                 # canonical test suite
├── requirements/          # base / ai / voice dependency sets
├── scripts/               # launcher helpers
├── setup_venv.py          # venv bootstrap (uv-based)
├── .env.example           # config template (copy to `.env`)
├── pyproject.toml
└── requirements.txt
```

## Voice (`asis/voice`)

Pluggable voice pipeline: audio input (microphone/sounddevice), VAD
(Silero, optional), wake-word detection (keyphrase/openwakeword),
speech recognition (faster-whisper, optional), speaker identification
+ embeddings, TTS (pyttsx3), audio output. Heavy audio/ML
dependencies are optional and lazily imported — base installs and
tests run without them. Scriptable mocks live in
`asis/voice/engines/mock.py`.

## Install

> **Fastest path (recommended):** one command does it all — venv (via
> `setup_venv.py`, uv-based), light dependencies, Ollama server start,
> model check, then the interactive REPL:
>
> ```bash
> npm run ASIS
> ```
>
> Useful variants: `npm run asis:voice` (voice loop; falls back to mock
> engines without the voice extra), `npm run asis:check` (fast boot
> probe), `npm run asis:test` (full suite), and `npm run ASIS --
> --message "hi"` (forward any flags after `--`). The launcher never
> auto-installs the heavy voice stack — for real audio run
> `uv pip install -r requirements/voice.txt` first. A launcher-owned
> `ollama serve` is stopped on exit; a pre-existing server is left alone.

Manual setup:

```bash
pip install -e .            # base
pip install -e ".[voice]"   # voice extras (microphone, STT, TTS, VAD)
```

## Configuration

One validated layer: `asis/configuration` → typed `settings` →
components. Copy `.env.example` to `.env` (or export variables
directly); see the example file for every variable, default, type,
and range.

```python
from asis.configuration import load_settings, settings

settings.ai.model          # typed access, never os.getenv in app code
fresh = load_settings()    # independent reload (tests/development)
custom = load_settings({"ASIS_AI_MODEL": "x"})  # explicit overrides win
```

Precedence: explicit overrides > process environment > `.env` >
built-in defaults. Empty values count as unset; present-but-invalid
values raise `ConfigurationError`. Paths resolve via `platformdirs`
outside the repository (overridable with `ASIS_*_DIRECTORY`).

## Chat behavior

Each REPL/voice run owns one `ConversationSession` (`AssistantApp`):
turns persist user + assistant messages within configured history /
context limits, relevant memories are retrieved query-scoped into the
system prompt (stored memory is data, never instructions). Tool use is
native-first: the local model receives tool definitions derived from
the active registry and may return structured calls (validated against
parameter schemas, at most `ASIS_TOOL_MAX_CALLS_PER_TURN` per turn),
falling back to the heuristic/explicit intent path when native calling
is unavailable — both converge on the same Router/permission path.
Failed inference preserves state; memory failure logs and continues.
Explicit `core:` user commands (`core:devices`, `core:device <id>`,
`core:status`, `core:service <svc> <op>`, `core:agent <op>`,
`core:data <type>`, `core:send <device> <type>`) execute one CORE tool
deterministically through the same Router/permission path.

## C.O.R.E. uplink (optional)

```text
A.S.I.S. -> integrations/core/ (RealCoreAdapter, CoreConnectionManager)
-> CORE-CLIENT (CoreDeviceClient) -> TCP+TLS -> CORE-HOST
```

1. Make `client.core_device_client` importable (sibling CORE-CLIENT repo
   or `PYTHONPATH`); repos stay unmerged, and A.S.I.S. never imports
   CORE-HOST modules (tested).
2. Provision the device on CORE-HOST (`provision-device`); copy only the
   public cert to the device — never `core.key`/`.pfx`.
3. Set `ASIS_CORE_ENABLED=true` (+ host/port/cert in `.env`; the
   provisioning credential is runtime-only, never filed).
4. `CoreConnectionManager` (a plain `RuntimeComponent`) connects
   (`CORE_HANDSHAKE` → auth → `DEVICE_REGISTER` → online). When
   disabled/unreachable everything local keeps working; CORE tools fail
   cleanly with `CORE_UNAVAILABLE`; reconnect is bounded and stop-aware.

CORE tools (`core_discover_devices`, `core_device_info`, `core_status`,
`core_data_request`, `core_service_request`, `core_agent_request`,
`core_send_to_device`) are registered on the shared `ToolRegistry` in
both GENERAL and CODING modes — one adapter, one connection.
Network tools are HIGH (confirmation-gated); results are redacted and
truncated to 8 000 chars before the model. Host device-to-device
routing is one-way, so `core_send_to_device` yields a timeout-shaped
result rather than a reply envelope. Intelligence stays local:
normal prompts/history never leave the device; Ollama remains the only
inference provider.

## Manual LAN validation (NOT PERFORMED)

Windows CORE-HOST (TLS listener) + Mac CORE-CLIENT/A.S.I.S./Ollama:
provision → configure → authenticate → register → online; start
A.S.I.S., confirm CORE status (`--core-status`), hold a local
conversation, invoke a CORE tool, confirm host receipt + response;
stop the host, confirm local operation survives; restore host, confirm
bounded reconnect; shut down, confirm session secrets destroyed.
Do not mark PASS until physically performed.

## Test

```bash
python3 -m pytest -q        # canonical suite (tests/)
npm run asis:test           # same suite via the one-command launcher
```

## CLI

```bash
pip install -e .      # installs the `asis` console script
asis                  # persistent interactive terminal (text/voice/docs/persona)
asis --help
asis --preview        # render the CLI interface layout and exit (no model, no boot)
asis --message "hi"   # single shot (default model qwen3:14b)
asis voice            # voice loop (mock engines by default)
python -m asis        # alias for the asis console script (works from source)
```

The interactive terminal follows the CLI reference (`CLI.jpeg`): a
status panel (MODEL / OLLAMA / MEMORY / TOOLS / VOICE), `You >` /
`A.S.I.S. >` message lines, `[TOOL]`/`[DONE]` activity badges,
`Attachments: @ name ×` chips, a mode toggle + `[+] Attach` composer,
and a persistent bottom strip.

Interactive commands: `/help`, `/mode [text|voice]`, `/upload <path>` /
`/attach <path>`, `/docs`, `/detach <name>`, `/clear-docs`, `/clear`,
`/exit`, `/quit`.

Multi-person identity + WhatsApp persona:
  - `/identity analyze <chat.txt>` — parse a WhatsApp export, build
    identities (baseline, styles, modes, timeline, persona).
  - `/identity show|questions|simulate|forget|export <name>` — inspect,
    ask open questions, preview a simulated reply, forget, or export.
  - `/identity answer <name> <answer>` — answer the top open question
    (stored as `USER_CONFIRMED`).
  - `/identity calibrate <name> <conversation>` — self-calibrate the
    persona against held-out replies (LLM predictions scored against
    observed text; persona version bumps on consistent mismatches).
  - `/personas` — list reconstructed identities.
  - `/persona <name>` — enter persona mode; every message is answered
    as that reconstructed identity (streamed, with a one-time privacy
    notice). `/persona off` exits.

ESC interrupts the response/speech; CTRL+C exits cleanly.
