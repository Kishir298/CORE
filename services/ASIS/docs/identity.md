# Identity reconstruction (asis/identities/)

Status: **Implemented + wired + tested** (`tests/test_identities.py`, 8 tests).
Pipeline: `parse -> store -> exchanges -> baseline -> micro/style -> modes/triggers/transitions -> timeline -> persona -> memory -> retrieval -> router -> simulator -> calibration`.

## Import
`/identity analyze <file>` parses full WhatsApp export (`[DD/MM/YY, HH:MM:SS] Sender:`),
multiline/media/deleted/system/malformed preserved, progress in `wa_progress`.
Never samples. Large files: streaming parse + chunked SQLite inserts.

## Identities
Multi-identity by `identity_id` (never display name). `match_identity` requires
alias + context; name-only max MEDIUM + confirmation. Incremental
`existing + evidence = updated` with change log; versions kept, rollback via
`persona_versions`.

## Memory
`memories` migrated (`identity_id, confidence, source, evidence`, `memory_events`).
Provenance: OBSERVED/INFERRED/EXTRAPOLATED/USER_CONFIRMED/UNKNOWN.
Classes: CORE/DYNAMIC/EVIDENCE/UNCERTAIN/USER_CONFIRMED/CALIBRATION.
Local SQLite canonical; RESCS export via `DomainRouter asis.memory.<id>`.

## Simulation
`AUTO/FORCE/ERA/COMPARE`. Targeted retrieval only. Consistency check
(style/length/emoji/mode/relationship/knowledge). Labeled
`AI reconstruction, not the actual person`. Never auto-contacts third parties.
`/identity forget` cascades identity + events (memories purged by identity_id).

## Calibration (target hidden)
`calibration_split 70/30 chronological` -> `generate(context)` without target ->
`compare (lexical/emoji/length composite)` -> `mismatch WRONG_MODE/...` ->
single flag / repeated investigate / consistent update. Held-out validation +
regression gate. No weight training (`qwen3:14b` unchanged).

## CLI
`/identities`, `/identity analyze|show|questions|simulate|forget|export <name>`.
All LLM-bypassed. Privacy: exports stay local, `platformdirs` outside repo,
no external upload.

NOT PERFORMED: live large-export soak (>50k msgs), embedding retrieval
(LIKE-only V1), real RESCS sync (placeholder adapter).
