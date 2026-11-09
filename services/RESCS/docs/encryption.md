# Encryption at Rest (Delegated Model)

RESCS does **not** implement application-layer encryption. This is intentional:
no homemade crypto, no keys beside data.

## Guarantees

- **Transport:** HTTPS required in production (terminate at ingress/LB).
- **Database:** rely on provider disk encryption (RDS/Supabase at-rest) or LUKS for self-hosted.
- **Blobs:** local volume encryption, or S3 SSE-S3/SSE-KMS when `RESCS_STORAGE_BACKEND=s3`.
- **Secrets:** `RESCS_API_KEY`, `RESCS_S3_*` via env/secret manager only. Never committed, never logged, never in `/health` or error details (tested).

## Key management

Owned by infrastructure: KMS key rotation per provider docs. RESCS has no key files to rotate.

## What is NOT claimed

No per-record envelope encryption. If compliance later requires it, use a vetted
AEAD (e.g. XChaCha20-Poly1305 via `cryptography`) with KMS-wrapped DEKs — out of
scope for v0.2/v0.3 and marked as future work.

