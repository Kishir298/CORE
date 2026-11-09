# A.S.I.S. Configuration

Single validated layer: `asis/configuration` → typed `settings` →
components. Application code must not call `os.getenv` (the only
exception is the generic `permissions/secrets.py:get_secret()` helper).

## Flow and precedence

```text
Built-in defaults            asis/configuration/defaults.py
        ↓
.env files                   project root + user config dir
        ↓
Process environment          ASIS_* variables
        ↓
Explicit overrides           load_settings(env={...})
        ↓
Environment parsing          strict, lazy, per call
        ↓
Typed Settings               frozen dataclasses
        ↓
Validation                   validate_settings() → ConfigurationError
        ↓
A.S.I.S. Components
```

`.env` files load with `override=False`: existing process variables
always win. Explicit `load_settings(env=...)` wins over everything.

## API

```python
from asis.configuration import load_settings, settings

settings.ai.model            # global singleton (frozen)
fresh = load_settings()      # independent reload, reads live env
custom = load_settings({"ASIS_AI_MODEL": "x"})
```

Settings dataclasses are frozen — mutation raises
`FrozenInstanceError`. Tests use `monkeypatch.setenv` + `load_settings()`
and never touch the global.

## Parsing rules

- Empty/whitespace-only values count as **unset** (default applies).
- Present-but-invalid values raise **`ConfigurationError`** naming
  variable, received value, and expectation — never silent fallback.
- Booleans accept `1/true/yes/on/enabled` and
  `0/false/no/off/disabled` (case-insensitive); anything else raises.

## Categories

| Section | Key fields |
|---|---|
| Identity | `name`, `title`, `shutdown_phrase`, `app_version` |
| Runtime | `debug`, `log_level` (`DEBUG…CRITICAL`), `shutdown_timeout` (>0) |
| AI | `provider`, `model`, `endpoint` (http(s) URL), `request_timeout` (>0), `temperature` (0–2), `max_context_messages`, `context_char_limit` (>0) |
| Conversation | `max_history` (>0) |
| Memory | `provider` (`local` only), `database_name` (safe filename) |
| Voice | audio (`sample_rate`, `channels`, `block_size` >0; `input/output_engine`), STT (`engine/model/device/compute_type`, optional `language`), TTS (`engine`, optional `voice`, `sample_rate`), speaker (`engine/model/device/metric`, `confidence/threshold` 0–1), wake (`engine`, `threshold` 0–1, `model` optional; `wake_word` required unless engine is mock/none/off), VAD (`engine`, `threshold` 0–1) |
| Network | `timeout` (>0), `retries` (≥0) |
| Tools | `timeout` (>0, per-run bound) |
| Web | `enabled` (bool, default on), `search_provider` (`duckduckgo` only), `timeout` (1–120), `max_results` (1–10), `max_chars` (500–50000), `max_response_bytes` (10000–5000000), `max_redirects` (0–5), `max_query_length` (1–2000), `max_url_length` (100–8000) |
| Translation | `enabled` (bool, default on), `provider` (`mock`/`madlad`), `model` (non-empty id), `model_path` (local dir, may be empty), `device` (non-empty, e.g. `cpu`), `cache_enabled` (bool), `cache_size` (1–10000), `default_source` (`auto` or code), `default_target` (code), `max_chars` (1–50000) |
| Calculator | `enabled` (bool, default on), `max_expression_chars` (100–20000), `max_matrix_size` (2–50), `timeout` (1–300), `precision` (0–30), `angle_mode` (`radians`/`degrees`/`gradians`) |
| Tool loop | `max_calls_per_turn` (1–10, native calls per turn) |
| AI native | `native_tools` (`auto`/`true`/`false`) |
| Coding | `default_mode` (`general`/`coding`/`translation`), `workspace` (dir at use), `command_timeout`/`max_file_size`/`max_output_size` (>0) |
| C.O.R.E. | `enabled` (bool, default off), `host` (non-empty), `port` (1–65535), `device_file`/`ca_file` (optional paths), `insecure` (bool), `connect_timeout`/`request_timeout` (1–600), `reconnect_enabled` (bool), `reconnect_delay` (0–300) |
| Security | `require_confirmation_for_dangerous` (strict bool) |
| Paths | `data/config/cache/logs/memory/runtime` (platformdirs, overridable) |

## C.O.R.E. uplink lifecycle

Standalone by default (`ASIS_CORE_ENABLED=false`). When enabled, the
`asis` and `asis voice` entry points build exactly one
`CoreConnectionManager` (one `RealCoreAdapter`, one CORE-CLIENT session)
and pass it to `AssistantApp`, so GENERAL, A.S.C.S. coding, and voice
share the same connection. The provisioning credential is runtime-only:
export `ASIS_CORE_CREDENTIAL` in the shell before starting — it is read
at connect time, never written to disk, logs, memory, or model context,
and never belongs in `.env` files. Without it (or when the host is
unreachable) A.S.I.S. runs fully locally and CORE tools report
`CORE_UNAVAILABLE`; shutdown always disconnects and clears the
ephemeral session.

## Paths

`platformdirs` on macOS/Windows/Linux; nothing persistent lives in the
repo. `runtime/` uses the OS temp dir; the rest live under the
platform's user data/config/cache roots. Any directory is overridable:

```text
ASIS_DATA_DIRECTORY, ASIS_CONFIG_DIRECTORY, ASIS_CACHE_DIRECTORY,
ASIS_LOG_DIRECTORY, ASIS_MEMORY_DIRECTORY, ASIS_RUNTIME_DIRECTORY
```

Overrides accept `~`, resolve to absolute paths, and fall back to
platform defaults when unset.

## Reference

`.env.example` documents all 96 settings variables with type, range,
and default (87 set explicitly; `ASIS_TRANSLATION_MODEL_PATH`,
`ASIS_CORE_DEVICE_FILE`, `ASIS_CORE_CA_FILE`, and the 6
`ASIS_*_DIRECTORY` path overrides appear commented-out since empty /
platform defaults apply). `ASIS_CORE_CREDENTIAL` is runtime-only and
never belongs in settings. Counts are cross-checked
against `settings.py` — if they ever disagree, the code wins and the
file must be fixed.
