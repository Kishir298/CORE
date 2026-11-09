# CORE Pi Server Setup and Changes

Release 0.5.0 | 6 November 2026

This release implements the Raspberry Pi direction in the updated RISARMS plan, including its ASIS and ASCS chapter. The Pi runs the portal, Python backend and RESCS together. Normal operation has no laptop dependency and does not replace Raspberry Pi OS.

Target: Raspberry Pi 5 8GB, Raspberry Pi OS Lite 64-bit, Python 3.11 or newer, systemd and an ext4 SSD mounted at /srv/core. Source and API tests ran on Linux x86_64. ARM64 installation, real Pi cold boot, temperatures and model performance remain acceptance tests. Treat the Pi deployment as experimental until those checks pass.

## What the combined ZIP contains

| Component | Release behavior |

| --- | --- |

| CORE HOST | Authenticated browser portal, owner approvals, account isolation and Pi AI scheduling. |

| RESCS | Separate private service and virtual environment; SQLite and file bytes on the SSD. |

| CORE CLIENT | Optional cross-platform native app with existing offline profiles, cached files and local AI fallback. |

| ASIS and ASCS | Pi adapters use tool-free assistance and code generation. Updated ASCS and existing ASIS source are bundled; their standalone runtimes remain separate. |

| Our Library and Day Quest | Owner-configured dashboard links. Separate apps, accounts, databases and installation packages. |

The previous hybrid frontend/laptop deployment is superseded for this Pi package. No shared temporary owner password is installed. First-run setup creates your owner account with a password you choose. Existing migrated accounts keep their identities and password hashes.

## Persistent directories

CORE state and chat data: /srv/core/core. RESCS database: /srv/core/rescs/database. File bytes: /srv/core/rescs/files. Logical Trash is tracked in CORE library.sqlite3; bytes stay in RESCS until permanent deletion. /srv/core/rescs/trash is reserved, not a second copy. Optional models use /srv/core/models. Our Library and Day Quest have separate reserved directories.

## Install and start the Pi services

Flash Raspberry Pi OS Lite 64-bit using Imager; set hostname core, your own SSH credentials and Asia/Dubai. Attach Ethernet and the SSD. Format only the independently verified data drive, then mount it by UUID at /srv/core using the earlier plan. The installer never formats a drive or changes fstab.

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip caddy avahi-daemon unzip
findmnt --mountpoint /srv/core
uname -m
python3 --version
```

The architecture must report aarch64, the SSD must be an ext4 mount with a UUID, and Python must be at least 3.11. Extract this ZIP on the Pi, enter its RISARMS-Portal folder and run:

```bash
sudo bash deployment/pi/install.sh
```

Installation creates separate risarms-core and risarms-rescs accounts/environments, root-only configuration in /etc/risarms, SSD directories and Caddy configuration. It checks dependencies and preserves existing environment files. Stop old services and back up before upgrading. Do not run the legacy hybrid installer.

```bash
sudo systemctl enable --now risarms-rescs risarms-core
sudo systemctl reload caddy
sudo systemctl status risarms-core risarms-rescs
sudo journalctl -u risarms-core -b --no-pager
```

Use the first-owner setup key from the protected journal at https://core.local. Choose your email and a new password of at least 12 characters. Before sending credentials, securely copy Caddy root.crt from /var/lib/caddy/.local/share/caddy/pki/authorities/local to each client and trust that certificate authority in its OS/browser trust store. Do not copy the CA private key. A local certificate warning is not a completed HTTPS setup.

If core.local does not resolve, check Avahi/mDNS and your router. Away from home, Tailscale is optional. Choose one canonical tailnet hostname, change both CORE_PUBLIC_ORIGIN in core.env and the Caddy site address, then restart CORE/reload Caddy and update clients. Keep TLS verification and private-network access. No public domain, router forwarding or remote infrastructure is provisioned by this package.

If the SSD is absent or has the wrong UUID, both data-writing services refuse startup. Mount dependencies stop them when the mount disappears. After restoring the SSD, use systemctl reset-failed and restart RESCS then CORE. Bounded restart retries prevent an endless crash loop.

## Prepare and admit local AI models

AI is optional. File access and login continue without a working model. Install Ollama separately from its official Linux instructions, keep its listener on loopback and dedicate that instance to CORE. Apply the supplied SSD, CPU and memory policy only after stopping Ollama:

```bash
sudo systemctl stop ollama
sudo bash deployment/pi/install-ollama-policy.sh
sudo systemctl enable --now ollama
```

The policy sets one loaded model, one parallel generation, 2048 context, two inference threads, a 60-second idle retention and lower CPU priority. The optional Ollama service gets CPUQuota=200%, MemoryMax=6G and TasksMax=128. These are starting limits requiring Pi measurement. Request payloads enforce the context. No warm-up prompts or automatic cloud fallback are sent.

| Tier | Available RAM gate | Default admission |

| --- | --- | --- |

| 0.5B Q4 | 2.5 GiB | Initial experiment after explicit benchmark approval |

| 1.5B Q4 | 3.5 GiB | Initial target after explicit benchmark approval |

| 3B Q4 | 5 GiB | Conditional ceiling after local load testing |

| 4B and 7B or larger | Not automatically admitted | Blocked in this Pi policy |

Use explicit qwen2.5 or qwen2.5-coder small instruct Q4 tags. The API verifies parameter size, quantization, completion capability and the installed full digest. Changing a tag digest, context or device invalidates approval. Downloads are explicit and are not included in the ZIP.

```bash
ollama pull qwen2.5:0.5b
sudo systemctl stop risarms-core
sudo risarms-admin pi-benchmark --model qwen2.5:0.5b
```

Review the smoke response, measured first-text latency and peak-memory estimate, then test real household tasks and web latency with the other websites running. Explicit approval reruns the probe:

```bash
sudo risarms-admin pi-benchmark --model qwen2.5:0.5b --approve
sudo systemctl start risarms-core
```

For ASCS, use an explicitly installed qwen2.5-coder tag and add --service ascs. Select the exact approved tag in portal Host settings models.asis or models.ascs. A smoke response does not prove tool reliability; execution remains disabled. A failed 30-second cold-start deadline is a failed benchmark, with no hidden retry.

## Resource controls and coding boundaries

Before every Pi job, CORE checks Linux MemAvailable, the dedicated Ollama cgroup limit/current usage, a 1.5 GiB reserve, model residency, conservative estimates and any larger measured peak plus margin. Swap does not qualify a model. Existing resident weights are not counted as a second full allocation.

Ten one-second CPU samples establish pressure. Sustained total CPU above 70%, high memory pressure, excessive load or temperature at least 80 C queues the job. Total CPU is used conservatively; this is not an exact non-AI CPU attribution. A maximum of eight outstanding jobs and one per account share one inference slot. Queue waits expire after two minutes. Unapproved models fail clearly, without automatic substitution or download.

Only previously approved resident models are unloaded before switching; unrelated residents require an explicit operator unload. The job then rechecks admission. A critical memory/temperature event cancels an active task; model failure or cancellation requests unload. No action is replayed automatically. CORE and RESCS have separate memory/process budgets. The configured Linux flock coordinates CORE with the updated standalone ASCS queue. View selected models, RAM, reserve, CPU pressure, context and allowed/queued/blocked reasons in the owner dashboard.

ASIS messaging has no tools. The owner ASCS Pi adapter generates text/code only and cannot inspect a repository, write files, run a shell or invoke compilers. Full ASIS tools, ASCS execution and TIVISS execution are not enabled by the Pi profile. Bundled standalone sources retain their separate functionality; ASCS itself requires Python 3.12+. ARM64 voice/native dependency support and an execution sandbox are not certified by this release.

## Accounts and private files

Registration creates a pending request. The owner approves members; approved members receive messaging and personal storage. Owner-only administrative APIs require an owner session, CSRF validation and password re-entry valid for five minutes. Re-entry is session-bound and rate-limited. It grants no access to other users’ private records, files, chats or jobs.

My files lists names, dates and sizes without fetching file contents. Preview fetches content only on request and displays bounded plain text; it never executes uploaded HTML. Download verifies the stored hash. Uploads support at most 8 MiB per file. Each account starts with a 250 MiB quota including Trash; the owner can set 8 MiB to 10 GiB through /api/quotas after reauthentication. The optional desktop cache retains its separate 250 MiB limit. RESCS 0.4 additionally verifies an expiring signed owner, HTTP method and path on every private storage request.

Folders are private by default. Explicit folder sharing grants read-only access to a named approved account; revocation blocks later requests. Shared uploads/deletes and inherited write permissions are not implemented. Delete moves a file to logical Trash; Restore recovers it; Delete permanently requests RESCS purge. A downloaded copy cannot be revoked.

## Migration backups and rollback

Do not point a new instance at old data while another instance is running. Stop all CORE/RESCS writers and take a complete backup of the old portal web directory, matching RESCS database and file objects. Preserve the original old installation until the new server passes account, record and hash checks.

The supplied migration utility supports a local SQLite RESCS source and requires a fresh Pi destination before its first start. It checks the SSD and stopped service state, verifies SQLite copies and creates a readable off-filesystem archive. Existing passwords and account IDs remain unchanged. Paths below are examples to replace with verified source locations:

```bash
sudo python3 deployment/pi/migrate.py \
  --old-web /path/to/old/web \
  --rescs-db /path/to/old/rescs.sqlite3 \
  --rescs-files /path/to/old/rescs-files \
  --backup-dir /mnt/separate-backup
```

The first run is a preflight. After stopping any external writers, repeat with --apply to copy data. A destination with accounts or file/database data is refused. The utility preserves the old source, transfers the matching RESCS key and keeps local first-install rollback staging. It does not migrate external PostgreSQL/S3 backends, client caches or separately installed applications. A failed partial migration requires inspection rather than an automatic retry.

For recurring backups, stop both services, copy /srv/core/core and /srv/core/rescs together plus /etc/risarms to a separate protected device/location, verify file hashes and archive readability, then restart RESCS and CORE. /srv/core/backups is only staging on the same SSD. Use encryption for off-device copies and keep decryption keys separately. Back up optional desktop profiles independently.

Test restoration into an isolated directory first. Check accounts.sqlite3 and the RESCS SQLite database with PRAGMA quick_check, verify a known file SHA-256 and restore with both services stopped. A full powered-off Pi restore has not been performed here. Roll back using matching software and data/configuration backups; do not mix an old binary with a partially migrated database.

## Separate applications and optional clients

Configure links.our_library and links.day_quest as verified HTTP(S) URLs in owner Host settings. The portal opens those applications separately; it does not merge authentication or proxy unknown APIs. No Our Library or Day Quest source was modified or exercised in this release. Never share raw RESCS folders through Samba; use a separate /srv/core/shared directory if needed.

The optional desktop client installs from CORE-CLIENT and retains core-client as its own command. It supports explicit offline record/file sync and local model fallback once dependencies and weights are provisioned. Browser use on the LAN requires no internet, but the browser itself has no service-worker offline cache; use the native app when disconnected from the Pi. Certificate trust for the native Python runtime must be configured as well.

## Validation and documentation handoff

Executed automated checks cover CORE regression behavior, direct API ownership boundaries, reauthentication, revocation/session expiry, folder sharing, logical Trash, quotas, low-memory/CPU admission, digest/context/device approvals, shared scheduling, cancellation and model switching. An integration test used the actual RESCS HTTP service, SQLite and object files, including gateway restart persistence. Unit checks simulate interrupted streams and disk-full writes. Exact counts and commands are in validation and VALIDATION.md in the ZIP.

The full CORE host suite ran from its own repository directory. Later resource-policy refinements have focused retest evidence. No claim is made that historical ASIS/ASCS full-suite results validate native ARM64 packages or models. The current model probe has not been run against real weights in this environment.

| Feature | Evidence and remaining limit |

| --- | --- |

| Portal and RESCS API | Linux x86_64 tests; actual Pi installation and mount removal still required. |

| Model admission and queue | Deterministic tests; real Pi CPU/RAM/thermal/latency measurements still required. |

| ASIS and ASCS on Pi | Tool-free adapters implemented; small-model responses require local approval. No arbitrary coding execution. |

| Browser layout | Responsive CSS retained; JavaScript syntax checked. Chromium visual run blocked by host socket restrictions. |

| Windows and macOS client | Source retained and regression checks recorded; native OS execution not performed in this release. |

| Boot and remote access | systemd/Caddy/mount configuration supplied. Physical cold boot, Tailscale and TLS trust are operator acceptance tests. |

Before household use: test Pi cold boot with the laptop off; missing/wrong/read-only SSD; RESCS/Ollama failure and recovery; concurrent file transfers; phone/tablet/laptop layout; certificate trust; separate app links; restart persistence; and off-device backup restoration. Measure web response latency, CPU, RAM, temperatures, power faults and exact model first-token/generation latency under the intended workload.

Add this guide, the source changes and VALIDATION.md to risarms-docs. New contracts include /api/reauth, /api/ready, /api/ai-status, /api/folders, /api/shares, /api/quotas and file preview/move/trash/restore/purge routes. /api/files/{id}/delete now means move to Trash. Existing /api/records, account UUID ownership and offline CAS sync are retained. Private root/OS administrators can inspect plaintext; client-side encryption remains deferred.

## Implementation references

Raspberry Pi OS: https://www.raspberrypi.com/documentation/computers/os.html

Ollama Linux and API: https://docs.ollama.com/linux and https://docs.ollama.com/api

Ollama concurrency and context: https://docs.ollama.com/faq

Caddy local TLS: https://caddyserver.com/docs/caddyfile/directives/tls

systemd mounts: https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html
