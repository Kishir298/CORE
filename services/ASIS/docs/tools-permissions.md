# Tools & Permissions

A.S.I.S. tools are controlled capabilities — the model never executes
shell commands or calls tools by itself. Application code routes
explicit tool requests through registry → router → executor.

## Tools

| Tool | Purpose | Permission | Status |
|---|---|---|---|
| `echo` | Repeat text back (empty input fails) | SAFE | Implemented |
| `current_time` | Current UTC date/time (`iso`, `timestamp`) | SAFE | Implemented |
| `read_file` / `search_files` / `list_directory` | Workspace inspection (bounded) | SAFE–LOW | Implemented (coding mode) |
| `git_status` / `git_diff` | Read-only repo state (`--stat`/`--cached` only) | SAFE | Implemented (coding mode) |
| `write_file` | Exact workspace write | HIGH | Implemented, confirm-gated (coding mode) |
| `run_tests` / `run_command` | Allowlisted `pytest`/`python`/`git`, `shell=False` | HIGH | Implemented, confirm-gated (coding mode) |
| `git_add` | Stage workspace paths | HIGH | Implemented, confirm-gated (coding mode) |
| `git_commit` | Commit (never pushes) | CRITICAL | Implemented, confirm-gated (coding mode) |
| `core_status` | Local CORE connection snapshot | SAFE | Implemented (needs CORE manager) |
| `core_discover_devices` / `core_device_info` / `core_data_request` / `core_service_request` / `core_agent_request` / `core_send_to_device` | C.O.R.E. infrastructure operations | HIGH | Implemented, confirm-gated (needs CORE session) |
| `web_search` | Web search, bounded structured results (`title`, `url`, `snippet`, `source`) | LOW | Implemented (optional, on by default) |
| `web_fetch` | Fetch readable text from a public HTTP/HTTPS page (bounded + metadata) | LOW | Implemented (optional, on by default) |
| `translate_text` | Offline translation (`text`, `target_language`, optional `source_language` → auto-detect) | LOW | Implemented (optional, on by default; mock backend by default) |
| `calculate` | Offline mathematics (`operation` + string args; exact + verified results) | LOW | Implemented (optional, on by default; SymPy-backed, stdlib only otherwise) |

## Web access (`asis/web/` + `asis/tools/provided/web_tools.py`)

`web_search(query, max_results)` and `web_fetch(url, max_chars)` travel
the exact same path as every other tool: native definitions from
`tool_definitions_for()` → `normalize_native_call()` → `ToolRouter` →
`PermissionManager`/authorizer → `ToolExecutor` → tool → `WebProvider`
(`asis/web/provider.py`, DuckDuckGo HTTP backend, no key, no browser).
No second framework exists for the web: A.S.C.S. coding mode and voice
use the same shared registry via `AssistantApp`.

Rules: only `http`/`https` (everything else → `WEB_UNSUPPORTED_SCHEME`);
SSRF protection resolves every hostname and re-checks every redirect hop
(`127/8`, `10/8`, `172.16/12`, `192.168/16`, `169.254/16`, `::1`,
`fc00::/7`, `fe80::/10`, `localhost` blocked → `WEB_BLOCKED_DESTINATION`);
bounded results (≤ configured max, default 5), download bytes (default
1 MB → `WEB_RESPONSE_TOO_LARGE`), returned chars (default 8 000,
`truncated: true`), redirects (default 3), URL/query lengths, and network
timeouts (`ASIS_WEB_TIMEOUT`). HTML is reduced to readable text with the
standard library only — no JavaScript, no downloads, no shell.

Web content is **untrusted data**: it reaches the model as information
inside `[tool … result]` context, never as instructions, and is never
auto-stored to memory. Errors use `WEB_*` codes (`WEB_DISABLED`,
`WEB_UNAVAILABLE`, `WEB_TIMEOUT`, `WEB_INVALID_URL`,
`WEB_UNSUPPORTED_SCHEME`, `WEB_BLOCKED_DESTINATION`, `WEB_HTTP_ERROR`,
`WEB_RESPONSE_TOO_LARGE`, `WEB_PARSE_ERROR`, `WEB_PROVIDER_ERROR`) with
sanitized messages (no keys, headers, cookies, IPs, or paths). When
`ASIS_WEB_ENABLED=false` both tools return `WEB_DISABLED` and everything
else (chat, memory, local tools, A.S.C.S., voice, CORE) keeps working.
Live-network tests are opt-in (`ASIS_WEB_LIVE=1`,
`tests/test_web_live.py`); the default suite never dials out.

No ungated dangerous tools ship today (HIGH/CRITICAL gated). `ToolResult(success, data, error,
tool_name)` is frozen; non-`ToolResult` returns are wrapped.

**Wiring status:** the tool subsystem is application-wired via
`AssistantApp` + `asis/app/actions.py` + `asis/app/native_tools.py`.
Preferred path is native function calling: the model receives tool
definitions derived from the active registry and returns structured
calls, each normalized to a validated `ToolRequest` (unknown tools,
malformed arguments, missing/wrong-typed/unknown parameters rejected)
and dispatched through `ToolRouter` → mandatory permission check →
`ToolExecutor`, bounded to `ASIS_TOOL_MAX_CALLS_PER_TURN` calls per
turn with a final plain generation. Fallback is the heuristic/explicit
path (structured JSON action in model output, or conservative
heuristics such as time questions → `current_time`) through the same
single-cycle `ToolRequest` dispatch. Results return explicitly to the
conversation and feed inference. Unknown tools, invalid arguments,
denials, timeouts and exceptions all become controlled failures, never
crashes. Model-generated `"confirmed"`/`"yes"` arguments are not
authorization and are rejected as unknown parameters before the
permission layer is reached. Direct `tool.execute()` (which bypasses
permissions/timeout) is never used by application code, and no
shell/subprocess path exists.

Mechanics (`asis/tools/`): `ToolRegistry` (thread-safe, rejects
duplicates with `ToolValidationError`), `ToolRouter` (unknown names
→ `failure("Tool not found")`, executor defaults to
`settings.tools.timeout`), `ToolExecutor` (authorization gate, then
run in a daemon thread joined on the timeout → `failure("Tool timed
out…")` on expiry; exceptions become failures; start/finish/deny
events published).

## Permissions (`asis/permissions/`)

Levels: `SAFE(0) < LOW < MODERATE < HIGH < CRITICAL`; confirmation
required at `HIGH+` via `request_confirmation()`, which auto-approves
when `settings.security.require_confirmation_for_dangerous` is false
and otherwise uses the console handler (literal `yes`; EOF/Ctrl+C
denies). Enforcement path: `Tool.authorizer` → executor denies with
`TOOL_DENIED` before anything runs. Coding writes, command execution,
git mutations and all networked CORE tools sit at `HIGH`/`CRITICAL`,
so confirmation is exercised in coding mode (see `docs/coding.md`).

`PermissionManager` (`asis/permissions/manager.py`) is the named
object facade over these primitives (`allows` / `require` /
`needs_confirmation` / `level`); its `.authorizer` plugs directly into
`ToolExecutor`, so manager-gated and callable-gated execution behave
identically. The model can never bypass it: every CORE tool result is
redacted and size-bounded before reaching model context.

Helpers: `resolve_sandbox_path()` jails relative paths
(`SandboxViolation` on escape); `get_secret()`/`require_secret()`
read process secrets without hardcoding names (missing required
secret → `ConfigurationError`); generic `require_*` validators.
