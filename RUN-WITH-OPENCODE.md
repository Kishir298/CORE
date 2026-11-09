# OpenCode prompt for the Pi release

Open this extracted RISARMS-Portal folder in OpenCode and paste:

```text
Deploy this exact combined RISARMS Pi release. First read README.md, VALIDATION.md,
docs/CORE-Pi-Setup-and-Changes-2026-11-06.md and deployment/pi/*. Do the work,
validate it and report actual results. Use the GitHub connector if available to
inspect related repositories, but do not replace these newer archive changes with
older GitHub code. This archive contains unreleased CORE updates and updated
RESCS/ASCS sources.

The target is Raspberry Pi OS Lite 64-bit on Pi 5 8GB. CORE frontend/backend and
RESCS belong on the Pi; the laptop is only the SSH/admin client. Get the actual Pi
SSH destination/key path from me if it is missing. Verify aarch64, Python >=3.11,
SSD model/UUID and the ext4 mount at /srv/core. Never guess a disk name, format a
drive, change fstab destructively, replace the OS or delete existing data. Stop
writers and create a verified off-device backup before migration or upgrades.

Install dependencies and run deployment/pi/install.sh only after the verified SSD
is mounted. Review the generated environments privately. Preserve existing API
keys/account hashes and matching RESCS data. Use the supplied preflight migration
utility only for its supported SQLite source and a fresh destination. Keep old
software/data for rollback. Do not expose raw API/model ports or print secrets.

Validate Caddy and service definitions, then enable/start risarms-rescs and
risarms-core. Test https://core.local using a properly trusted local CA. Never
solve certificate errors by disabling verification. Complete first-owner setup
with a newly chosen password through the protected browser flow. Verify approval,
member/admin isolation, password re-entry, metadata-only listings, upload,
preview/download hashes, folders/read shares, revocation, Trash/restore/purge,
quotas and restart persistence. Ensure rejected API requests do not expose another
account's file names, bytes or chat logs.

AI is optional. Install Ollama only if requested, apply the supplied Pi policy and
keep it private. No silent weight downloads or cloud fallback. Pull an explicitly
chosen small Q4 tag, stop CORE for the exclusive local benchmark and measure exact
digest/context, available RAM, peak memory and latency with other websites active.
Do not approve a model until I have reviewed the actual results. Start at 2048
context/two threads/one inference. Keep 4B/7B+ blocked. ASCS in the portal must
remain code-generation-only; no shell, compiler, repository editing or full-agent
execution without an independently tested OS sandbox. Cooperate with the shared
root-owned inference flock used by updated ASCS; do not start a second queue or
kill unrelated models.

Configure Our Library/Day Quest only from their actual verified local endpoints;
keep their accounts/data/installations separate. Tailscale is optional. Do not
publish a public endpoint, purchase anything or alter router forwarding implicitly.

Run actual Pi acceptance checks: cold boot with the laptop off, absent/wrong SSD,
backend/model crash, explicit recovery, phone/tablet/laptop browser layout, storage
persistence and backup restoration. Benchmark RAM/CPU/thermal/power/web latency.
Keep unexecuted checks clearly marked. Update a private deployment handoff document
with exact changes, commands, service names, URLs, paths, test evidence, remaining
limits and rollback steps, ready for risarms-docs. Return the actual working URL
and daily start/stop/status commands only after observing them work.
```
