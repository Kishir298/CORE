# Release validation

6 November 2026. Linux x86_64, Python 3.12. Source code, controlled failures and actual loopback services were used. This is an experimental Pi deployment; no actual ARM64 execution or physical hardware test was performed.

| Suite | Passed | Skipped | Failures |
| --- | ---: | ---: | ---: |
| CORE-HOST-pi-release | 840 | 0 | 0 |
| CORE-CLIENT-pi-final | 200 | 0 | 0 |
| RESCS-pi-final | 312 | 4 | 0 |
| pi-final-contracts | 65 | 0 | 0 |

The final full host suite includes the updated signed RESCS adapter, catalog, short-context inference payload and new privacy/resource tests. The earlier full host run passed 837 tests before the final signed-scope and queue refinements; its evidence is retained separately. The final focused contract suite overlaps the full suite and is not an additional count of distinct tests.

The client initially had a test-fixture failure: a relocated Python binary was incorrectly represented by a bare symlink. The fixture now copies the executable and writes a real pyvenv.cfg; the offline file and whole client suites passed. This was a fixture correction, not a production workaround. A runtime Tcl library path was supplied for this container's tests.

RESCS tests skip three optional live PostgreSQL checks and one optional S3 check; the Pi target uses SQLite/local files. The ASCS full suite was attempted with its supplied offline_guard.py, but automatic approval review blocked it for an attempted api.openai.com connection. No passing full-suite result is claimed and no retry/bypass was performed. RISALIVE was not enabled. These controlled tests do not establish actual model quality or ARM64 performance. The bundled ASIS/TIVISS standalone sources were not re-audited in full in this Pi task; earlier release results do not certify them for Pi execution.

Clean isolated installation passed from declared portable SQLite dependencies, with installed CORE and RESCS commands invoked outside the source tree. First-owner setup, password re-entry, real signed-scope record/file round trips, private readiness and absence of a PostgreSQL dependency were checked. No model weights were downloaded.

ARM64 CPython 3.13 manylinux binary dependencies resolved/downloaded for CORE PyYAML plus the pinned RESCS requirements. This checks distribution availability, not importability or execution on Pi. A complete ARM64 wheelhouse is not included.

Ruff F checks, Python compilation, shell syntax and browser JavaScript parsing passed. systemd-analyze verify reported the expected unprovisioned /opt commands and missing srv-core.mount in this container; no systemd service boot was executed. It is not labelled a passing deployment verification. Chromium visual execution was blocked by a system socket permission error. Phone/tablet/browser layout, TLS trust, Tailscale, actual SSD failure, cold boot, power/thermal behavior and live inference remain operator acceptance checks.

## Reproduction

Run host/client pytest from their repository directories. For real RESCS tests set CORE_TEST_RESCS_PYTHON to an installed RESCS interpreter; otherwise those tests explicitly skip. RESCS requires its test dependencies (including the version-compatible httpx2/httpx test client). For ASCS, execute its validation/offline_guard.py before importing pytest, then run its suite. Deployment helper checks live under deployment/pi/tests. Unit resource/mount/disk-full fixtures are controlled scenarios; they do not emulate a physical SSD unplug.

Current commands and exact results are in the corresponding XML/log files. Test archives do not include setup keys, server tokens, live credentials or prompt-process logs.
