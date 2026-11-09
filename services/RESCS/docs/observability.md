# R.E.S.C.S. Observability

Operational visibility for R.E.S.C.S.: request correlation, health semantics
and safe logging.

## Request correlation (`X-Request-ID`)

* Every HTTP response echoes a request id under `X-Request-ID` (header name
  configurable via `RESCS_REQUEST_ID_HEADER`, default `X-Request-ID`).
* A caller-supplied id (trimmed, non-empty, ≤128 chars) is honoured;
  missing/empty/overlong ids fall back to a generated `uuid4().hex`.
* The id is available in-process via `rescs.observability.request_id_var`
  and on the ASGI scope as `rescs.request_id` (survives `ServerErrorMiddleware`
  handling of unhandled exceptions).
* Error responses — including `401/404/422/500/503` and health `503`s — carry
  the same header. Middleware adds it on `http.response.start`; exception
  handlers add it as a fallback so unhandled `500`s are still correlated.
* `GET /health/*` responses always carry the header.

## Health semantics

| Endpoint | Success | Failure | Auth |
| --- | --- | --- | --- |
| `GET /health/live` | `200 {"status":"alive",service,version}` | never fails on deps | public |
| `GET /health/ready` | `200 {"status":"ready",checks:{database:ok,storage:ok}}` | `503 {"status":"not_ready",checks:{...down...}}` | public |
| `GET /health` | `200 {service,version,status:ok,checks}` | `503` same shape with `down/degraded` | public |

* `HealthService` aggregates named checks (`ok|degraded|down`); any `down`
  dominates, then `degraded`; raising checks count as `down`.
* Database probe: `SELECT 1` connectivity check. Storage probe: put/get/delete
  round-trip of a `_rescs_probe_<uuid>` blob. Both swallow exceptions to
  `down` — no SQL, connection strings or tracebacks in responses.
* Unknown routes return `404 {"error":{"code":"NOT_FOUND",...}}`; unhandled
  failures return `500 {"error":{"code":"INTERNAL_ERROR",...}}` without
  leaking internals.

## Logging

* Access log (`rescs.access`): `request_id method path status duration_ms`
  per request, including `503/500` paths. `path` excludes query strings;
  headers, bodies and stored values are never logged.
* Lifecycle logs (`rescs.main`): start/stop, backend name (e.g. `sqlite`,
  `postgresql` — never the full URL) and schema version.
* Error logs (`rescs.api.errors`): unhandled errors log the exception type
  via `logger.exception` for server-side diagnosis; clients receive only the
  generic envelope.
* Never logged: `X-API-Key`, `Authorization`, `DATABASE_URL`, passwords,
  tokens, record `value`/`metadata` contents or file bytes.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `RESCS_REQUEST_ID_HEADER` | `X-Request-ID` | response/request correlation header |
| `RESCS_LOG_LEVEL` | `INFO` | `DEBUG\|INFO\|WARNING\|ERROR\|CRITICAL` |

