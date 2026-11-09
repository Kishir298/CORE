# AI, Conversation, Memory

## Providers (`asis/ai/providers/`)

Abstract contract `AIProvider`: `name`, `model`, `chat(messages)`,
`stream_chat(messages)`, `available()`. Two implementations exist:

| Provider | Status | Details |
|---|---|---|
| `mock` | Implemented (tests/dev) | `MockAIProvider`: scripted responses, `fail`/`delay` knobs, offline; optional scripted `tool_sequences` enable native-call tests |
| `ollama` | Implemented (needs `requests` + a local Ollama server) | Local server: model/host/timeout/**temperature**/**retries** from settings; `temperature` sent as chat `options` only when set; `available()` probes `/api/tags` with a capped probe timeout (fast offline/down detection); native function calling via `/api/chat` `tools` (`supports_native_tools=True`, model-dependent). Lifecycle: already-running servers are external and never stopped; `ASIS_OLLAMA_MANAGED=auto` (default) starts an owned `ollama serve` only when down (`asis/ai/ollama_lifecycle.py`). Boot sends one silent `hello` probe through the same provider instance (`think=False`, small `num_predict`, no tools/context) before `You >` (`asis/app/boot.py`). Down server → deterministic `InferenceError` (no cloud fallback, no auto-download); use `ASIS_AI_PROVIDER=mock` for fully offline runs without Ollama |

No Hugging Face or cloud providers exist — anything else is future.

`create_provider()` (`asis/ai/manager.py`) selects by
`settings.ai.provider`; unknown names raise `InferenceError`.
`AIManager` wraps chat/streaming with `AI_INFERENCE_STARTED/FINISHED/
FAILED` events. The CLI provider helper passes model/host/timeout/
temperature/retries from settings, matching the manager path.

## Inference (`asis/ai/inference.py`)

```text
Input → Orchestration → Context Construction → Prompt Construction
→ Model Inference → Response Parsing → Final Response
```

`InferenceEngine.generate()` = interrupt-check → assemble messages →
single `manager.chat()` → interrupt-check. No retries at this layer
(retries live in `OllamaProvider.chat`), no tool invocation, no
agentic loop. `generate_streamed(history, on_chunk)` delivers provider
chunks to the terminal as they arrive (true streaming path:
Ollama → provider → engine → CLI renderer); `generate_and_stream()`
yields per-chunk with per-chunk cancellation. qwen3 `<think>` blocks
(and the `thinking`/`reasoning` message field) are stripped into
`metadata["thinking"]` and never rendered. Cancellation tokens reset
at each turn boundary (`reset_turn()`), so one ESC never poisons the
next request. All failures surface as `InferenceError`.

## Orchestration (`asis/ai/orchestrator.py`)

Deterministic, rule-based pre-inference planning — no second LLM, no
fabricated chain-of-thought. `build_plan()` classifies each message
(`GENERAL_CHAT/QUESTION/TASK/TOOL_REQUEST/CODING/CALCULATION/
TRANSLATION/DOCUMENT_QUERY/MEMORY_QUERY/CORE_OPERATION/
VOICE_INTERACTION/UNKNOWN`) and decides memory/document/tool needs,
mode, and response constraints. `AssistantApp.chat_streamed()` runs the
plan, then the unchanged tool/permission flow; only the final
user-visible generation streams. `GENERAL_CHAT` (greetings, repeat-back
like `say exactly Hi`) skips the native function-calling attempt for a
fast single generation; all other intents (including `QUESTION`) keep
the native-first path so natural questions (`what is 6 times 7`,
`core status?`, `search the web`) can still use tools. Natural math
(`times/plus/minus/divided`, `compute`, `what is <n>`) and web verbs
(`search/fetch/look up`) classify to `CALCULATION`/`TOOL_REQUEST`.
Live-tested with `qwen3:14b`
(single-turn + direct name recall PASS 2026-09-18; generic
"What did I just tell you?" phrasing is model-flaky despite verified
memory context — see Final Report notes).

## Native function calling (`asis/ai/tool_schemas.py`, `asis/app/native_tools.py`)

The model may request tools through the provider-native protocol
instead of text heuristics. Tool definitions are derived
deterministically from the active-mode `ToolRegistry`
(`ToolDefinition`: name, description, JSON-Schema parameters; sorted,
secret-vocabulary rejected). `OllamaProvider.chat_with_tools()` renders
them into `/api/chat` `tools` and parses `message.tool_calls` into
`NativeToolCall` records (malformed entries dropped, never raised);
`AIProvider.supports_native_tools` advertises the capability (default
`False`, so incapable providers use the heuristic fallback).

`AssistantApp.chat()` order per turn: explicit `core:` command →
native loop (intent-filtered definitions → validate each call against
its schema → `ToolRouter` → `PermissionManager` → `ToolExecutor`, at
most `ASIS_TOOL_MAX_CALLS_PER_TURN` validated calls, then a final plain
generation) → heuristic fallback (`parse_tool_request`, unchanged
single cycle). Intent-aware tool selection (`select_tool_definitions`,
deterministic orchestrator hint):

```text
GENERAL_CHAT (hi, say exactly Hi)  → 0 tools (skip, plain generation)
explanation QUESTION                → 0 tools ("none" verdict)
  (explain/tell me about/describe/what is|are/why/how-does-it-work,
   small-talk — and zero tool-signal stems)
CALCULATION                         → {calculate} (~678B)
TOOL_REQUEST time|echo|translate    → single matching tool
TOOL_REQUEST web                    → {web_search, web_fetch} (~612B)
CODING                              → full coding set (mode router)
CORE_OPERATION / TRANSLATION        → deterministic bypass (no model call)
ambiguous QUESTION / any TASK /     → full general set (~2020B)
VOICE / MEMORY / DOCUMENT / unknown    (conservative: never starve)
```

Calls outside the filtered set are rejected as `unknown_tool` before
permission/execution. Both paths converge on the same `ToolRequest` and
the same permission boundary; filtering is optimization only — the
model only requests, A.S.I.S. authorizes.
`ASIS_AI_NATIVE_TOOLS` (`auto`/`true`/`false`, default `auto`) controls
the attempt; small local models that ignore `tools` simply fall back.
Limitations: multi-step depth is bounded by configuration, and native
support varies by Ollama model — fallback coverage is intentional, not
a gap. Latency (measured 2026-09-18, `qwen3:14b` 9.3GB on this host):
`GENERAL_CHAT` (no tool definitions sent, `think=false`, streaming)
answers in seconds; tool-enabled turns send intent-filtered tool
definitions (calc ~64% smaller, web ~71%, time/echo ~92% vs the full
~2020B general set) and run up to `max_calls_per_turn` (default 3, each
tool ≤30s) plus a final generation — observed ~100s cold, faster warm
via `keep_alive=30m`. Tool results re-injected as context are capped at
4000 chars/call (`…[truncated N chars]`; small results byte-identical).
Native tool decisions stay buffered (`chat_with_tools` is `stream=false`
by design — Ollama partial-JSON `tool_calls` assembly would be fragile);
only the final plain generation streams. Remaining tool-turn latency is
model/hardware-bound, not application overhead.
Worst-case bound per turn: `request_timeout` (120s) × (1+retries) per
LLM call × up to 4 calls + tools. `GENERAL_CHAT` skipping the native
attempt is what keeps greetings/repeat-backs fast.

## Conversation vs memory

```text
Conversation Context  ≠  Permanent Memory
   (per-session, bounded)      (SQLite, persistent)
```

- `ConversationSession`: in-memory turn list, tail-trimmed to
  `max_history` (no token counting).
- `ContextAssembler`: labeled bounded system prompt — `SYSTEM:` (stable
  identity/personality) + `MODE:` + `CAPABILITIES:` (tool names, no
  schemas) + query-scoped memory/docs + `CONSTRAINTS:` (orchestrator,
  max 8 lines) + fixed `MEMORY RULES` + `BEHAVIOR` (never invent,
  data-vs-instructions, prefer tools); total capped at
  `context_char_limit` (stable head kept when it fits, otherwise hard
  bound wins; dynamic tail truncated with `[context truncated]` marker).
  History tail-sliced to `max_context_messages`; history itself is
  never char-truncated. `estimate_size()` reports prompt length.

**Wiring status:** `ConversationSession` + `ContextAssembler` +
`InferenceEngine` are wired into the normal CLI and voice paths via
`AssistantApp` (`asis/app/assistant.py`), which owns one session per
REPL/voice run. Each turn persists user + assistant messages (bounded
by `max_history` / `max_context_messages`); failed inference preserves
state without inserting a phantom assistant turn; the `inference`
interrupt scope stays cancellable.

## Memory (`asis/memory/`)

| Piece | Status |
|---|---|
| `MemoryManager` (remember/recall/search/forget) | Implemented |
| SQLite file storage (`memories` table, category/importance index) | Implemented |
| LIKE search (`importance DESC, created_at DESC`) | Implemented (no embeddings/vector search) |
| Auto-extraction (`my name is…`, `I like…`, `I'm building…`) | Implemented (`asis/app/memories.py`, invoked by chat CLI) |
| Recall into prompts | Implemented + wired — `search_context()` keyword retrieval injected via `ContextAssembler`; empty → normal inference; failure → log + continue; generic recall phrasing ("what did I just tell you?") falls back to top-importance memories |
| Cloud sync | Future — R.E.S.C.S. responsibility, not A.S.I.S. |

Database lives at `settings.paths.memory / settings.memory.database_name`
(default `memory.db`); only the `local` provider exists
(`build_memory()` rejects anything else with `ConfigurationError`).
Tests use a temp-DB fixture; no cloud, no internet.
