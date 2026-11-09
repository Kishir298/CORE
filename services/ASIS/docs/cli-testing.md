# CLI, Testing, Dependencies, Development

## CLI

Installed entry point `asis` (`pyproject.toml [project.scripts]`).
`python -m asis` is supported as an alias (`asis/__main__.py`).

Bare `asis` launches the persistent interactive terminal (TEXT/VOICE,
documents, typing effect) on top of the existing `AssistantApp` runtime:

```text
A.S.I.S.  ● ONLINE  (header + MODEL/MODE/OLLAMA status bar)

You
┌─ hello ─┘

A.S.I.S.
└─ Hello! How can I help?

>
```

`asis` flags: `--version`, `--identify`, `--provider {mock,ollama}`,
`--model MODEL` (default `qwen3:14b`), `--memory-db PATH`,
`--list-tools`, `--core-status`, `--message TEXT` (single shot),
`--mode {general,coding,translation}`, `--workspace PATH`, `--debug`,
`--log-level LEVEL`. Normal interactive use defaults to a quiet console
(WARNING); `--debug` restores verbose logs. File logging is preserved.

Interactive slash commands (handled by the CLI, never sent to the LLM):
`/help`, `/mode [text|voice]` (bare `/mode` toggles), `/upload <path>` /
`/attach <path>` (`.txt .md .pdf .docx .csv .json`), `/docs`,
`/clear-docs`, `/clear`, `/exit`, `/quit`. Keys: ENTER submit, ESC
interrupt response/speech (app stays alive), CTRL+C exit cleanly with
terminal restore. Documents persist across text/voice switches and are
injected as bounded offline context (4k chars/doc, 12k total).

Interrupt semantics (implemented, deterministically tested):
ESC sets a stop flag, cancels all `InterruptCoordinator` scopes
(`inference`/`voice`/`tools`), stops TTS + audio output, and returns
the prompt immediately. Cancellation is cooperative: chunk boundaries,
VAD/STT stages, and the typing renderer observe it. Blocking Ollama
HTTP (`requests.post`) cannot be safely killed mid-socket, so it stays
bounded by the configured request timeout; the UI does not wait for
it — the orphaned worker is a daemon thread whose late result is
discarded and never touches conversation/tool/terminal state.
CTRL+C is delivered to the main loop through a thread-safe
`shutdown_event` (a background watcher thread cannot raise
`KeyboardInterrupt` in the main thread); shutdown stops TTS/audio,
stops the watcher (joining it), restores POSIX `termios` state in a
`finally`, runs runtime cleanup, and exits `0`.
Physical TTY ESC/CTRL+C timing is unit-tested with mocks only;
manual TTY validation is recorded as NOT PERFORMED unless physically
exercised (see validation status below).

Document resource bounds (implemented, deterministically tested):
files over 10 MB are rejected before reading (`stat` gate); text/JSON
reads are capped at 2 MB; PDF extraction stops after 2 MB of text;
DOCX archives with more than 64 entries or a `document.xml` over
2 MB are treated as empty rather than extracted. All parsing is
offline (stdlib-first, optional `pypdf`/`python-docx`).

Validation status (this environment):
`python -m asis --version/--help` live-tested; persistent mock-provider
session live-tested (multi-turn, `/mode voice|text`, `/docs`,
`/clear-docs`, `/upload`, `/exit`, exit `0`); installed `asis` console
script verified equivalent via the `entry()` argv path (no binary on
PATH in this container — run `pip install -e .` to install it).
REAL OLLAMA VALIDATION: PERFORMED 2026-09-18 (`qwen3:14b` present,
`available()=True`): `asis --message "hi"` → visible greeting;
`say exactly Hi back to me` → `Hi.`; `What are you?` → A.S.I.S.
identity; `What can you do?` → capabilities (math/time/translation/
web/general); multi-turn `My name is LiveTestUser` → `What is my
name?` → `LiveTestUser` (memory write + query-scoped recall PASS).
Historical note: an earlier validation environment had only a stale
`qwen2.5:3b` cache and CPU inference exceeded the window — that model
is NOT a default and MUST NOT be used. REAL VOICE HARDWARE VALIDATION:
NOT PERFORMED (no audio hardware/deps; mock pipeline tests cover
the path).

`asis translate` subcommand (offline translation REPL/single-shot):
`--to LANG`, `--from LANG|auto`, `--message TEXT`, `--provider`,
`--model`, `--memory-db PATH`. REPL supports `/tr-to`, `/tr-from`,
`/mode` (see `docs/translation.md`).

`asis calculate` subcommand (offline deterministic math): positional or
`--expression TEXT`, `--operation OP` (30 engine operations),
`--equation/--equations/--variables/--variable/--function/--arguments/`
`--value/--from/--to/--data/--angle-mode`, repeatable `--param KEY=VALUE`.
Exit `2` with a `CALCULATION_*` code on failure
(see `docs/calculator.md`).

`asis voice` flags: `--stt-engine`, `--stt-model`, `--tts-engine`,
`--tts-voice`, `--speaker-engine`, `--wake-word`, `--no-wake-word`,
`--provider`, `--model`, `--memory-db PATH`, `--mode`, `--workspace`,
`--max-turns N`
(`0` = infinite), `--debug`. Mock engines by default; voice startup
failures exit `2` unless `--debug` re-raises.

## Testing

```bash
python -m pytest -q        # full deterministic suite (no HW/net/GPU)
python -m pytest tests/test_cli.py tests/test_interactive.py tests/test_cli_hardening.py -q
python -m pytest tests/test_voice.py tests/test_voice_runner.py tests/test_ollama_model_default.py -q
```

> Canonical result: **789 passed, 10 skipped (2026-09-23)** — verify with `python3 -m pytest -q`. Counts below are approximate per-file snapshots, not a substitute for the runner.

| File | Approx tests | Covers |
|---|---|---|
| `test_configuration.py` | ~49 | defaults/overrides/precedence/validation/paths/voice/coding |
| `test_calculator.py` | ~62 | offline calculator engine, 30 ops, SymPy verification |
| `test_translation.py` | ~54 | offline translation, 136 langs, detection/providers |
| `test_web.py` | ~89 | web search/fetch, SSRF guard, bounded provider |
| `test_native_tools.py` | ~33 | native function-calling, router/permission convergence |
| `test_assistant_app.py` | ~20 | session/memory/tools wiring, fail-open, permissions |
| `test_interactive.py` | ~27 | REPL, docs attach, shutdown, interrupts |
| `test_offline.py` | ~15 | offline-first guards, network boundaries |
| `test_core_*.py (7 files)` | ~60 | RealCoreAdapter, connection, tools, e2e (LAN NOT PERFORMED) |
| `test_voice_*.py` | ~40 | pipeline/engines/runner, mock-only; hardware NOT PERFORMED |
| `test_cli.py` | ~8 | entry point, flags, REPL shutdown, memory building |
| + remaining (permissions, memory, tools, events, identity, shutdown, etc.) | ~250 | see runner for exact split |

Mock providers everywhere: **no Ollama, microphone, speakers, GPU,
models, internet, CORE, or RESCS required**. No coverage gate is
configured (`pytest-cov` is installed but no threshold set) — do not
claim 100% coverage.

## Dependencies (`pyproject.toml`, `requires-python = >=3.11`)

- **Core (mandatory):** `platformdirs`, `python-dotenv`, `sympy`
  (local offline math; see `pyproject.toml`/`requirements/base.txt`).
- **AI (optional):** `requests` (the Ollama provider uses HTTP via
  `requests`; the `ollama` client package is not used). A base install
  without extras still runs the mock/offline CLI: `OllamaProvider` is
  imported lazily and only actual Ollama or web-tool execution needs
  `requests` (proven by `tests/test_base_install.py`).
- **Voice (optional):** `numpy`, `scipy`, `sounddevice`, `soundfile`,
  `silero-vad`, `faster-whisper`, `torch`, `torchaudio`, `speechbrain`,
  `openwakeword`, `pyttsx3` (+ `pycaw/comtypes/pywin32` on Windows).
- **Docs (optional):** `pypdf`, `python-docx` (`requirements/docs.txt`,
  `pip install -e ".[docs]"`). Parsers fall back to stdlib-only
  extraction when these are absent.
- **Dev:** `pytest`, `pytest-cov`, `ruff`, `black` (line-length 88;
  ruff rules `E,F,W,I,UP,B,SIM`).

Heavy packages stay optional via lazy imports — base install and
tests never touch them.

## Development workflow

```bash
pip install -e ".[dev]"     # pytest, ruff, black
python3 -m pytest -q        # test
ruff check asis tests       # lint (must pass)
ruff format --check asis tests  # format
```

`setup_venv.py` bootstraps a local venv. `ASIS.code-workspace`
points VS Code at `.venv` with `pytestArgs=["tests"]`.
