# Tests — RESCS

`unit/` (offline SQLite/memory/FakeS3), `api/` (httpx TestClient), `integration/` (gated Postgres/S3 skip without env).
Run `.venv/bin/python -m pytest tests/unit/test_config.py -q` for smoke. See `../README.md`, `../docs/deployment.md`.

