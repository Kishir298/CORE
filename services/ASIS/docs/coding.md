# A.S.C.S. Coding Capability (`asis/coding/`)

A.S.C.S. (**A Smart Coding System**) is a **capability/mode inside
A.S.I.S., not a separate AI model or runtime**. One `AIManager` +
one loaded model serves both modes; switching modes changes system
instructions, context providers and tool registries only.

## Modes

| Mode | Value | Behavior |
|---|---|---|
| `GENERAL` (default) | `general` | Normal assistant: identity + memory context, `echo`/`current_time` tools, no repo injection |
| `CODING` (A.S.C.S.) | `coding` | Engineering assistant: coding instructions + `REPOSITORY CONTEXT` + 10 coding tools |
| `TRANSLATION` | `translation` | Offline translation: deterministic local translation turns (see `docs/translation.md`) |

Mode lives on `AssistantApp.mode` (`asis/app/modes.py: AssistantMode`,
`parse_mode()`); profiles in `asis/app/profiles.py`. `set_mode()` flips
an attribute — provider/model instance untouched (proven by tests).

## Switching

```text
> /mode coding        # or /ascs
A.S.C.S. coding mode enabled.
Workspace: /path/to/project

> /mode general
A.S.I.S. general mode enabled.

> /mode               # prints current mode
```

Flags: `asis --mode {general,coding,translation} --workspace PATH`,
`asis voice --mode ... --workspace ...`. No auto-detection by design;
explicit selection always wins.

## Workspace

Explicit, bounded, validated (`asis/coding/workspace.py`):
`ASIS_CODING_WORKSPACE` or `--workspace` or launch CWD; must be an
existing directory. Every file op resolves via the existing
`resolve_sandbox_path` — `../`, absolute outsiders and symlink escapes
are rejected with `SandboxViolation` / safe `ToolResult.failure`.

## Coding context

`CodingContextResolver` builds a bounded `REPOSITORY CONTEXT:` block
(workspace path, top-level tree, `git status --short`) injected through
the existing `ContextAssembler` provider chain. Repository facts are
labeled authoritative over stale memory; personal memory
(`"My name is ..."`) stays in the separate memory section.

## Coding tools (shared registry → router → executor)

| Tool | Permission | Notes |
|---|---|---|
| `read_file` | SAFE | bounded read |
| `search_files` | LOW | capped matches, skips binary/hidden |
| `list_directory` | SAFE | capped entries |
| `git_status` / `git_diff` | SAFE | read-only (`--stat`/`--cached` only for diff) |
| `write_file` | HIGH | exact write, confirm-gated |
| `run_tests` | HIGH | `python -m pytest -q`, confirm-gated |
| `run_command` | HIGH | allowlist `pytest`/`python`/`git`, `shell=False`, CWD=workspace |
| `git_add` | HIGH | workspace-relative paths only |
| `git_commit` | CRITICAL | message ≤500 chars, never pushes |

Command execution: allowlisted argv, workspace CWD, `timeout` =
`ASIS_CODING_COMMAND_TIMEOUT`, stdout/stderr capped at
`ASIS_CODING_MAX_OUTPUT_SIZE` with truncation flags. Structured
`ToolResult`s; no raw tracebacks to the model. Never auto-push, never
force-push, never rewrite history.

## C.O.R.E. in coding mode

A.S.C.S. shares the ONE `CoreConnectionManager`/`RealCoreAdapter` with
GENERAL mode — no second client, no second connection. When an
`AssistantApp` carries a core manager, all seven CORE tools
(`core_status`, `core_discover_devices`, `core_device_info`,
`core_data_request`, `core_service_request`, `core_agent_request`,
`core_send_to_device`) are registered on the coding router alongside
the workspace tools, under the same executor/confirmation policy.
CORE access cannot bypass workspace boundaries: coding tools still
validate every path against the workspace root, and CORE tools never
touch the local filesystem.

## Native function calling

A.S.C.S. uses the same native tool infrastructure as GENERAL mode:
coding tools carry parameter schemas, the model may call them
natively, and every call is validated and permission-gated through the
shared router — one tool architecture, mode-specific tool sets.

## Configuration

| Variable | Default | Validation |
|---|---|---|
| `ASIS_DEFAULT_MODE` | `general` | `general`/`coding`/`translation` |
| `ASIS_CODING_WORKSPACE` | _(empty → CWD)_ | existing dir at use time |
| `ASIS_CODING_COMMAND_TIMEOUT` | `120` | positive int |
| `ASIS_CODING_MAX_FILE_SIZE` | `200000` | positive int |
| `ASIS_CODING_MAX_OUTPUT_SIZE` | `60000` | positive int |

## Voice

Voice uses the same mode-aware `app.chat()` path (`process_fn`);
no second voice stack. A text `/ascs` switch applies to later voice
turns sharing the app.

## Limitations

Single tool action per turn (no agent loop); keyword-bounded search
(no embeddings); diff/status reflect the live repo at call time.
