# RISARMS Portal for the Raspberry Pi

Release 0.5.0, 6 November 2026. This combined source package replaces the mandatory laptop backend with a standalone Pi server. Raspberry Pi OS Lite 64-bit stays installed. CORE and RESCS run as separate private services on the SSD. Browser access is primary; RISARMS-UI (the canonical desktop application) and CORE-CLIENT (native protocol client) provide optional offline-capable access.

Read **docs/CORE-Pi-Setup-and-Changes-2026-11-06.docx** or its Markdown equivalent before installation. Read **VALIDATION.md** for executed checks and hardware limits. This is an experimental ARM64 deployment, tested as source on Linux x86_64; it is not a preflashed OS image or a certified Pi appliance.

## Install on the Pi

Use a Raspberry Pi 5 8GB with active cooling, suitable power, Ethernet and a separately verified ext4 SSD mounted by UUID at `/srv/core`. Use Python 3.11+; the separate full ASCS runtime requires 3.12+. No installer formats a drive or edits fstab.

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip caddy avahi-daemon unzip
findmnt --mountpoint /srv/core
uname -m
python3 --version
# From this RISARMS-Portal folder:
sudo bash deployment/pi/install.sh
```

The installer requires `aarch64`, a mounted writable ext4 SSD and its UUID. It preserves existing environment files, refuses live-service upgrades, installs software and units, and leaves service enable/start to you. Migrate existing data before the first start; see the guide and `deployment/pi/migrate.py`. Review `/etc/risarms/core.env` and `/etc/risarms/rescs.env` without printing keys to shared logs.

```bash
sudo systemctl enable --now risarms-rescs risarms-core
sudo systemctl reload caddy
sudo systemctl status risarms-core risarms-rescs
sudo journalctl -u risarms-core -b --no-pager
```

Open **https://core.local** after trusting Caddy's local root CA on the client. Securely copy only `root.crt` from `/var/lib/caddy/.local/share/caddy/pki/authorities/local`; never copy its private key or disable TLS verification. Use the protected first-run setup key to create your owner account with a new password. No shared owner credential is shipped. Existing migrated password hashes remain valid.

A missing/wrong/read-only SSD blocks startup. Runtime mount removal stops writers; the updated RESCS also checks its required mount on HTTP requests. After recovering the mount, use `systemctl reset-failed`, then restart RESCS and CORE. The static frontend returns a clear API-unavailable error while the backend is down. No laptop, browser window or desktop session is required on the Pi.

## AI preparation

Messaging and storage are independent. Install Ollama explicitly using its official Linux instructions, then stop it before applying `deployment/pi/install-ollama-policy.sh`. This provisions SSD model storage and a service drop-in. It never downloads models.

```bash
sudo systemctl stop ollama
sudo bash deployment/pi/install-ollama-policy.sh
sudo systemctl enable --now ollama
ollama pull qwen2.5:0.5b
sudo systemctl stop risarms-core
sudo risarms-admin pi-benchmark --model qwen2.5:0.5b
# Review output and benchmark responsiveness under the intended household workload.
sudo risarms-admin pi-benchmark --model qwen2.5:0.5b --approve
sudo systemctl start risarms-core
```

Configure the approved exact tag in owner Host settings `models.asis`. For owner code generation, prepare a matching `qwen2.5-coder` tier and benchmark with `--service ascs`, then set `models.ascs`. No real model benchmark was run for this delivery.

Pi policy starts at 2048 context, two inference threads, one active inference, one loaded model and 60-second idle retention. Every job needs an approved installed digest/context/device receipt. Small tiers are 0.5B, 1.5B and conditional 3B; 4B/7B+ are blocked. Effective memory, reserve, resident weights, ten-second CPU pressure, load, PSI and temperature control admission. The dashboard reports reasons. The queue holds up to eight jobs, one per profile, with a two-minute wait limit. No silent model substitution, preload prompts, remote fallback or action replay occurs.

The shared root-owned `/run/risarms-inference/queue.lock` coordinates CORE with updated standalone ASCS. Other managed callers must cooperate with that same lock. Only approved resident models are unloaded during a CORE model switch; unrelated residents require explicit operator action.

**ASCS generates code only in the Pi portal. It does not execute code or edit repositories.** Full ASIS tools, full ASCS execution and TIVISS execution are blocked by this privacy profile until an actual sandbox/ARM64 runtime is validated. Their standalone sources are retained. Updated ASCS has its own protected Pi path; its manifest and thresholds differ from CORE's centralized tool-free adapter. Do not run its full legacy engine as the CORE/RESCS account.

## Files and privacy

The browser includes metadata listings/search, explicit plain-text preview/download, 8 MiB uploads, private folders, explicit read-only folder shares, Trash/restore and permanent purge. The initial account quota is 250 MiB including Trash; owner `/api/quotas` may set 8 MiB to 10 GiB. File bytes stay in RESCS; folder/share/trash metadata is in CORE `library.sqlite3`. Back them up together. Legacy files without catalog entries appear in the account's My Files root.

Owner admin routes require password re-entry for five minutes; this never grants private content belonging to other accounts. The gateway derives identity from the session and signs per-request RESCS owner/method/path assertions. ROOT/OS operators can inspect plaintext; client-side encryption remains deferred. Keep ports 8780 (HTTPS API), 8781 (loopback event channel), 8081 and 11434 private.

Browser use over your LAN requires no internet. When disconnected from the Pi, use RISARMS-UI for cached files/records, device credentials and provisioned local AI; there is no browser service-worker cache. Native certificate trust must also be configured. `core-host`, `core-client` and `rescs` remain separate installed commands. Use systemd to manage Pi daemons and `sudo risarms-admin` for service-account diagnostics/benchmarking.

## Other applications and remote access

Set verified `links.our_library` and `links.day_quest` URLs in owner Host settings. These apps retain separate installations, accounts and data. This package does not contain their source or merge authentication. Never share raw RESCS directories with Samba.

Tailscale is optional for private away-from-home use. Configure a single canonical tailnet hostname consistently in Caddy, `CORE_PUBLIC_ORIGIN` and clients, and retain certificate trust/HTTPS. No public URL, DNS, cloud subscription or router forwarding is created here.

## Package contents and handoff

- Complete CORE-HOST and CORE-CLIENT source, plus current RESCS 0.4 and updated ASCS source; standalone ASIS/TIVISS source.
- Separate systemd environments and one combined Pi installer; no model weights or ARM64 wheelhouse.
- Setup/change DOCX and Markdown, `RUN-WITH-OPENCODE.md`, integration prompts, provenance and validation evidence.
- Universal CORE/CLIENT/RESCS wheels under `install`; dependencies still require installation or an architecture-matched offline wheelhouse.

For offline provisioning, prepare all dependency wheels on a matching Python/OS/architecture before disconnecting. ARM64 Python 3.13 binary dependency resolution was checked; that is not ARM64 execution. Back up old software, accounts, RESCS DB/files and protected configuration before migration or upgrades.
