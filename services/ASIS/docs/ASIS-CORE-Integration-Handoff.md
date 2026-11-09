# ASIS CORE Integration Handoff

Release 6 November 2026. This document is ready to copy into risarms-docs. It replaces the October handoff for this release. ASIS remains usable independently of CORE on Windows, macOS and Linux. The new Raspberry Pi deployment profile is opt-in and experimental until benchmarks run on the actual Pi.

## Changes and source contracts

The supplied RISARMS-Portal-Setup-and-Changes.docx calls for an independent Pi 5 8GB server, protected website capacity, tool-free member messaging and owner-controlled local models. This release implements admission control and supplies a separate CORE-HOST patch. It does not deploy a portal or approve a model's quality or performance.

Source baseline: Kishir298/ASIS commit 16976ed2215d26c8ca08d64fda49ad16389aaa5d, overlaid with the previously delivered ASIS-CORE-Integrated-2026-10-21 source changes. The actual CORE-HOST-Linux-RISARMS-Portal-2026-11-04 ZIP, core/web/services.py, gateway.py, chat_worker.py, portal.html and the RESCS integration contract were inspected. The attached Word document's later Pi requirements take precedence over its older deployment guidance.

The installed setuptools entry point remains `asis = asis.cli.main:entry`. Legacy `python -u -m asis --mode general --workspace PATH --memory-db PATH --message=TEXT [--model=MODEL]` remains supported. Output flushes while streaming; failure returns nonzero, cancellation returns 130, and CORE retains process-group cleanup. A failed stream is not automatically replayed.

New files: `asis/pi/{__init__,policy,runtime,worker,cli}.py`, `tests/test_pi_policy.py`, `deploy/pi/{core-pi.conf,ollama-pi.conf,pi-models.example.json,benchmark-record.example.json}`. Changed provider/CLI/mode files integrate the policy; `tests/test_offline.py` distinguishes local resource readings from network telemetry; HTTP response test doubles now implement close. CI installs the tested extras and uses a valid OS/Python matrix. The live workflow gates individual steps through environment variables rather than an invalid job-level secrets expression. Existing October fixes to profile paths, streaming, cancellation and offline voice preparation are retained. `docs/ASIS-CORE-Changed-Files.txt` lists every source difference from GitHub.

The GitHub email identified CI run 38208233008: Python 3.12 failed in lint with 19 F-series errors, before tests ran. Those lint repairs are retained and the identical lint command passes locally. GitHub has not been updated or rerun by this delivery.

## Architecture and permissions

CORE authenticates users and constructs allowlisted subprocess commands. In Pi mode, members run `asis.pi.worker --kind chat`: direct model messages with no ASIS agent, tools, shell or CORE uplink. Owner ASIS uses the normal general assistant and its existing permitted tool set. Owner ASCS uses `asis.pi.worker --kind code`, returning code as text. Arbitrary code execution is refused until an enforceable OS sandbox is implemented and validated. This release does not implement that sandbox. Members cannot launch ASCS. TIVISS is explicitly blocked in Pi mode until its inference joins this policy; running it outside the shared gate would invalidate the capacity guarantee.

All these Pi workers acquire the same Linux flock before loading or generating. Admission samples CPU for 10 seconds, reads MemAvailable, memory PSI, normalized load, thermal sensors and finite cgroup-v2 ancestor memory limits. Missing or invalid readings fail closed. The budget is the lower of host available RAM and cgroup remaining memory. Reserve is 1.5 GiB. Estimated peak is the maximum of the tier estimate, configured peak and observed peak plus 20 percent. A verified already-resident copy of the selected digest is credited once, avoiding a second full model charge.

| Tier | Verified parameter ceiling | Equivalent pre-load available RAM gate | Minimum estimated peak |
| --- | --- | --- | --- |
| small | 0.7B | 2.5 GiB | 1.5 GiB |
| initial | 1.8B | 3.5 GiB | 2.5 GiB |
| ceiling | 3.3B and benchmark approval | 5 GiB | 4 GiB |

These are conservative starting policies, not measured Pi capacity. CPU average above 70 percent, normalized load above 1, PSI some avg10 above 10 or temperature at least 80 C queues the request. Queue waits are bounded at 180 seconds, excluding an already-running blocking sample or metadata call. RAM insufficiency blocks immediately. Each request explicitly sets two model threads, 2048 context tokens and at most 256 generated tokens. Context 4096 needs a benchmark approval. 4B and 7B+ are refused by this implementation; a separately reviewed policy change and benchmark would be needed for 4B. No automatic model download, cloud fallback or mock inference is allowed in Pi mode.

The manifest pins an exact installed quantized tag and 64-hex digest. Tags and show metadata must verify size, quantization and completion capability. Native tool calls additionally need tools capability and explicit `tools_verified: true`; actual tool quality remains a hardware/model benchmark responsibility. Existing general-mode tools retain their existing permissions. This policy is a resource gate, not a security sandbox for the trusted owner.

Use a dedicated loopback Ollama service. Pi mode refuses automatic daemon startup if that service is unavailable, even when managed startup was configured. Other resident models are unloaded and verified absent under the lease; the selected model is unloaded on completion/cancellation. No retry replays actions. All participating services must use one queue path and the same trusted OS account. An external Ollama client can bypass the cooperative lock; restrict backend access and do not run unmanaged AI jobs. Backend single-generation/single-loaded-model settings add protection, not a cross-process security boundary. Pressure can change after admission; this release does not preempt an active generation or guarantee website latency.

## Prerequisites and persistent storage

Standalone needs Python 3.11+ and the requested extras. Local inference also needs separately installed Ollama and prepared local weights. Pi deployment targets Raspberry Pi OS Lite 64-bit, Pi 5 8GB, active cooling, adequate power and SSD. cgroup v2, /proc memory PSI and readable thermal sensors are required. cgroup v1 is unsupported in Pi mode. No laptop is needed after installation; model and dependency preparation may use another connected machine.

Mount the SSD persistently at `/srv/core` by its filesystem UUID using the OS disk tools and /etc/fstab. Verify with `findmnt --mountpoint /srv/core`. The supplied systemd drop-ins require that mount and refuse startup if it is absent, rather than writing into the underlying microSD directory. Review and test mount-failure behavior on the actual Pi before production. They assume CORE's existing `core.service` runs as user/group core and Ollama's installed `ollama.service` runs as user/group ollama. Adapt real unit names and identities before using them.

After confirming the mount, create paths:

```bash
sudo install -d -m 0700 -o core -g core /srv/core/core
sudo install -d -m 0750 -o ollama -g ollama /srv/core/models
sudo install -d -m 0755 /etc/core /opt/asis
```

Store CORE accounts, profile contexts and portal configuration under `/srv/core/core/web`; store model blobs/manifests under `/srv/core/models`. Source and virtual environments may live under `/opt`. The shared transient queue is `/run/risarms-ai`; it contains a lock and owner diagnostics, never prompts. CORE systemd RuntimeDirectory creates it as core with mode 0700. CORE must be stopped before moving existing data from /var/lib/core/web; preserve ownership and verify the backup before changing its path. No automatic migration modifies user databases.

## Install and PATH on each OS

Extract the complete release. The following commands assume the shell is initially inside its ASIS source folder. One-time installation may use Python; daily use is `asis` from any directory. Version stays 0.1.0 for compatibility, so identify the build by the release date/checksums and reinstall it explicitly.

Windows PowerShell:

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
py -m pipx install --force ".[ai]"
# Open a NEW terminal after ensurepath
Get-Command asis
asis --help
asis setup --model YOUR_EXACT_INSTALLED_TAG
asis doctor
asis doctor --check-model
asis
```

macOS and Linux desktop:

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
python3 -m pipx install --force '.[ai]'
# Start a new login shell after ensurepath
command -v asis
asis --help
asis setup --model YOUR_EXACT_INSTALLED_TAG
asis doctor
asis doctor --check-model
asis
```

If OS-managed Python rejects pip installation, install pipx through that OS's package manager, then run `pipx ensurepath` and `pipx install --force '.[ai]'`. pipx's command directory is normally ~/.local/bin; use `pipx environment --value PIPX_BIN_DIR` to verify it. Persist that exact directory in the Windows User Path settings, ~/.zprofile on macOS zsh, or ~/.profile on Linux. Do not replace PATH. Check stale launchers with `where.exe asis` on Windows and `type -a asis` on POSIX. `asis doctor --json` shows resolved directories. `asis setup` preserves an existing .env; edit its reported profile-specific file if the old model remains selected. Doctor without --check-model performs no network probe; --check-model verifies availability, not inference quality.

No arguments starts the normal standalone terminal interface. Optional interfaces remain `asis tui` or `asis --tui` after installing `[tui]`. Existing local calculator, translation, coding, voice and model interfaces remain available outside the Pi restrictions; their tools, weights, audio devices and optional extras must be installed. Windows-specific device/COM tools remain Windows-only. Audio capture/playback, GPU acceleration and wake-word libraries need target-specific drivers/packages and hardware validation. This release does not claim untested OS or hardware parity.

## Pi installation and CORE patch

Keep an ASIS source checkout at `/opt/asis`; CORE currently checks the source worker file and selects `/opt/asis/.venv/bin/python` when present. Install base plus AI into that virtual environment, with root review as needed:

```bash
python3 -m venv /opt/asis/.venv
/opt/asis/.venv/bin/python -m pip install '/opt/asis[ai]'
# Optional installed-command link for the service host
sudo ln -s /opt/asis/.venv/bin/asis /usr/local/bin/asis
asis --help
```

The release includes `CORE-HOST-Pi.patch` and exact replacement files under `core-patch/CORE-HOST`. Apply ONLY to the inspected 4 November source, keeping a backup:

```bash
cd /path/to/CORE-HOST
patch --dry-run -p1 < /path/to/release/core-patch/CORE-HOST-Pi.patch
patch -p1 < /path/to/release/core-patch/CORE-HOST-Pi.patch
# Reinstall CORE if its virtual environment is not an editable source install
/opt/core/venv/bin/python -m pip install --force-reinstall --no-deps .
```

Changed CORE files: `core/web/services.py` selects guarded workers; `core/web/gateway.py` adds authenticated owner-only GET /api/ai-status; `core/web/portal.html` adds an owner Settings status button; `tests/test_pi_inference_status.py` verifies the HTTP permission boundary. CORE-CLIENT needs no protocol change for portal messaging; native-client/Pi integration has not been executed. No ASCS or TIVISS repository source is changed. Original CORE behavior remains when the Pi deployment environment variable is unset.

Review `/etc/core/core.env`: remove any conflicting old CORE_WEB_DATA or set it to `/srv/core/core/web`. EnvironmentFile entries override Environment directives in systemd. Do not set a public origin or enable tunnels for local-only use. Install the drop-ins:

```bash
sudo install -d /etc/systemd/system/core.service.d /etc/systemd/system/ollama.service.d
sudo install -m 0644 /opt/asis/deploy/pi/core-pi.conf /etc/systemd/system/core.service.d/pi.conf
sudo install -m 0644 /opt/asis/deploy/pi/ollama-pi.conf /etc/systemd/system/ollama.service.d/pi.conf
sudo install -m 0640 -o root -g core /opt/asis/deploy/pi/pi-models.example.json /etc/core/pi-models.json
sudo systemctl daemon-reload
# Finish model approval below before starting AI jobs
sudo systemctl restart ollama core
sudo systemctl status ollama core --no-pager
```

These commands assume source files were copied to /opt/asis and existing services were installed using their reviewed installers. They have not been executed against systemd/Pi hardware here. Review the existing HTTPS proxy and remote hosting settings separately; ASIS startup never configures public ingress.

## Prepare and approve models explicitly

The manifest example is intentionally INVALID and admits no model. On a connected preparation host, explicitly select and download an instruct quantized model and copy its complete Ollama model store (manifests and blobs) to the SSD with correct ollama ownership. Set OLLAMA_MODELS consistently before using Ollama CLI. Do not copy only a display name or a single unreferenced blob. The release includes no weights and chooses no substitute model.

On the Pi, inspect the locally installed server with bounded calls:

```bash
curl --max-time 5 http://127.0.0.1:11434/api/tags
curl --max-time 5 http://127.0.0.1:11434/api/show -d '{"model":"YOUR_EXACT_TAG"}'
sudoedit /etc/core/pi-models.json
```

Replace the example key with the exact tag, digest with /api/tags digest, and choose the matching tier. Confirm instruct suitability from the model's actual template/model documentation; size metadata alone cannot establish it. Start with an approved 0.5B–1.5B model. Record real peak memory, CPU, temperature, token rates, concurrent website latency, cancellation and model-switch behavior using the benchmark template. Approve 3B/4096 only after those measurements. Never set tools_verified until successful owner tool tests and malformed-tool failure handling are demonstrated. Do not expose backend port 11434 publicly.

After approval, owner Settings selects that exact tag separately for ASIS and ASCS. Member ASIS is text-only; owner ASIS retains general-mode tools; owner ASCS returns code text. The new Settings status button displays admission model/digest/context/RAM/reserve/CPU/pressure and reason. The last result is a snapshot, not a continuously sampled monitor. Completion replaces it with idle metadata; a blocked request retains its resource readings and actual reason. No prompt or conversation text is included.

For a standalone guarded Pi worker, run as the core account with the shared trusted paths:

```bash
export ASIS_DEPLOYMENT_PROFILE=pi ASIS_CORE_ENABLED=false
export ASIS_PI_MODEL_MANIFEST=/etc/core/pi-models.json
export ASIS_PI_QUEUE_DIRECTORY=/run/risarms-ai
export ASIS_DATA_DIRECTORY=/srv/core/core/standalone
asis pi-status
asis pi-status --sample --model YOUR_EXACT_TAG
asis pi-chat --profile-dir /srv/core/core/standalone --model YOUR_EXACT_TAG --message 'Hello'
asis pi-chat --profile-dir /srv/core/core/standalone --model YOUR_EXACT_TAG --kind code --message 'Write a function as text'
```

Persist these non-secret settings in the selected profile configuration or service environment. RuntimeDirectory exists while core.service runs; for standalone use without CORE, create the same queue directory with the standalone account's ownership, or configure a private persistent queue path shared by every participating standalone process. Do not run another account against the same backend with an unrelated queue. `asis --mode general --model YOUR_EXACT_TAG --message='Hello'` uses the normal assistant through the same guard. Pi coding mode is refused explicitly. Help is available for pi-status and pi-chat.

## Isolation persistence and configuration

CORE supplies all six paths per profile: ASIS_DATA_DIRECTORY, ASIS_CONFIG_DIRECTORY, ASIS_CACHE_DIRECTORY, ASIS_LOG_DIRECTORY, ASIS_MEMORY_DIRECTORY and ASIS_RUNTIME_DIRECTORY, under its `profiles/USER_ID/asis/` subtree. Workspace and SQLite memory are explicit profile paths. Profile overrides exclude source/default-user .env loading; invalid supplied paths fail instead of using a shared default. Member workers keep bounded local chat-context.json; ASCS code generation uses a distinct codegen-context.json. Only completed replies update context atomically. --no-memory disables loading/saving worker context; CORE's existing persist=false also suppresses its task transcript. Worker stderr explicitly reports local or disabled persistence.

ASIS_CORE_ENABLED=false prevents recursive connections. CORE's launch environment does not pass member RESCS credentials. ASIS local memory is not claimed to be synchronized to RESCS: its adapter is still a placeholder. CORE portal records use its real server-side RESCS storage API and trusted account namespace contract. Local ASIS/worker operation does not depend on that remote store. The existing CORE portal account/record workflows may still require RESCS; this patch does not redesign those workflows into an offline database. CORE-owned task transcripts and worker history are different local files; back up both.

New configuration: ASIS_DEPLOYMENT_PROFILE=pi enables the opt-in policy; ASIS_PI_MODEL_MANIFEST selects the owner-maintained approval file; ASIS_PI_QUEUE_DIRECTORY selects the shared host queue; ASIS_AI_ENDPOINT selects loopback Ollama. Request metadata calls have 5-second socket timeouts, refuse redirects and proxies, and cap metadata bodies at 2 MiB. Pi generation also disables proxies/redirects and automatic retries. Its ordinary read timeout is 120 seconds for the text worker; normal ASIS uses its configured request timeout. A socket read timeout is not a total wall-clock generation budget; CORE retains its existing job timeout/cancellation control.

## Offline preparation and feature matrix

The included wheelhouse-linux-aarch64-py311 contains resolved base/AI dependency wheels for CPython 3.11 Linux ARM64, plus the platform-independent ASIS wheel. It excludes voice/TUI/docs extras and model weights. Wheel resolution succeeded on Linux x86_64; ARM installation has not run. For another Python/OS/architecture or extras, prepare matching wheels on a compatible connected machine:

```bash
python -m pip wheel --no-deps . --wheel-dir wheelhouse
python -m pip download --only-binary=:all: --dest wheelhouse '.[ai]'
# On the offline machine, use the transferred ASIS wheel and matching dependencies
python -m pip install --no-index --find-links wheelhouse 'asis[ai]==0.1.0'
```

The source-based download example may require a build backend during preparation; build the application wheel first and download its dependencies before disconnecting. On Pi CPython 3.11, use the supplied release wheel plus supplied ARM wheel directory with --no-index --find-links. Transfer the Ollama ARM64 executable/service installation and the entire chosen model store separately. Prepare document/voice extras, binaries and local weights independently if required. No voice model download is performed implicitly; test every chosen engine with network access disabled before handoff.

| Feature | Offline after preparation | Connection needed |
| --- | --- | --- |
| CLI setup, doctor without model probe, calculator, profile files | Yes | None |
| Local inference, Pi admission and loopback server | Yes | Local loopback only, no Wi-Fi/internet required |
| Local model/voice/document tools | Where dependencies, weights and devices support it | None for genuinely local engines |
| Translation | Depends on selected backend and installed model | External backend needs its network; no fake result |
| CORE portal from another device | With reachable LAN and its configured backend | LAN/remote network; existing record API depends on RESCS availability |
| Internet search, web fetch, external APIs | No | Respective reachable internet service |
| Downloads, updates, remote storage | No | Respective package/model/storage service |

## Backup rollback and validation

Stop jobs before backup. Back up the complete SSD CORE data tree, each standalone profile, /etc/core/core.env and pi-models.json, proxy settings and systemd drop-ins to trusted encrypted storage. Stop ASIS while copying SQLite, including any WAL files, or use SQLite's online backup API. Never distribute account databases, session secrets or real environment files in release ZIPs. Restore permissions/ownership and exact model manifest/blobs together; queue files are transient and should not be restored. Validate with doctor and a local task before re-enabling remote access.

Rollback: stop CORE jobs; restore the previous ASIS source/wheel and the backed-up CORE files (or reverse the patch against the exact release); remove the Pi drop-ins and unset ASIS_DEPLOYMENT_PROFILE; daemon-reload and restart only after reviewing the resulting paths. Preserve the SSD data and profiles. Do not accidentally restore the old /var/lib path or enable unconstrained ASCS on the Pi. No destructive schema migration is introduced.

Execution environment: Linux x86_64, Python 3.12.14. ASIS full suite, F-series lint and compilation were executed; exact results are in release-evidence.json and evidence/ reports. CORE portal tests use real loopback HTTP/auth/process behavior with deterministic storage/model fixtures. New Pi tests use simulated resource snapshots and a simulated Ollama HTTP server; they exercise real sockets and process locks but do not validate model quality. Offline dependency installation/launcher smoke checks are recorded separately. The GitHub CI matrix is configured for Windows/macOS/Linux and Python 3.11–3.13; it has not run for this release. Live voice/web/translation and sibling-client tests remain skipped where prerequisites are absent.

Blocked checks: actual Pi/ARM64 execution, real Ollama inference on Pi, thermals/power/cooling, SSD failure startup, cgroup behavior under production units, public ingress, native CORE-CLIENT, RESCS deployment, cross-OS hardware parity, arbitrary-code sandbox and website latency under model load. This is an implemented and tested experimental Pi adapter, not a claim that the complete Pi portal deployment is production-validated.

Ollama API references: https://docs.ollama.com/api/chat ; https://docs.ollama.com/api/ps ; https://docs.ollama.com/faq . Verify the installed server version supports the required metadata/capabilities and options; unsupported metadata fails closed.
