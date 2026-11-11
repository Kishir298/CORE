# CORE Security

## Reporting

Report vulnerabilities privately to the repository owner. Do not open a public
issue containing exploit details, credentials or device data.

## Implemented controls

- Owner/administrator and normal-user roles with separate storage and
  authenticated administration.
- Passwords are never stored in plaintext; only salted verifiers are stored.
- Device registration, verification, revocation and expiring sessions.
- User isolation: users cannot read another user's files or profile.
- Local portal mutations require allowed Host, same-origin and CSRF
  validation plus a JSON content type.
- Trusted session authentication is carried separately from untrusted JSON so
  a payload cannot spoof its identity.
- Device protocol versions are negotiated; unsupported versions are rejected.
- TLS failures are surfaced as `DeviceClientError`, never silently downgraded.
- API keys and provisioning credentials are runtime-only, redacted from logs
  and never written to prompts or event summaries.
- Release artifacts carry SHA-256 checksums; SBOMs are generated per release.
- GitHub Actions use least-privilege permissions; the publish job alone has
  `contents: write`.

## Credential storage

- Host: owner verifier and account records live under the private data
  directory; `gateway.json` is written atomically.
- Client: only the portal URL is saved. API and device credentials are
  supplied at runtime through the environment and are not persisted by the
  installer.
- Never commit `.env` files, `*.pem`, `*.key`, device JSON or release bundles;
  see `.gitignore`.

## Hardening notes

- Host and client listeners bind to loopback by default. Exposing the portal
  publicly requires an HTTPS reverse proxy and `CORE_PUBLIC_ORIGIN`.
- AI/model features are optional; ordinary CORE operation does not depend on
  model availability.
- AI inactivity shutdown, resource limits and local-model selection are
  configurable in the portal.

## Known limitations

- macOS builds are not signed or notarized unless signing credentials are
  configured.
- Dependabot/CodeQL are not enabled in this repository; add them if the
  organization enables GitHub Advanced Security.
