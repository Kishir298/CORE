# CORE Pi changes and resolved issues

6 November 2026. Scope: revised CORE package built against version 2 of the supplied
planning document and the dated RESCS 0.4 / ASCS Pi updates. Paths below are relative
to this combined package. This is not a claim of fresh line-by-line certification
of every standalone service or of a physical Pi deployment.

| Previous issue or mismatch | Implemented change | Main source |
| --- | --- | --- |
| Portal required the laptop backend | Pi serves static frontend and Python backend locally with separate RESCS | deployment/pi/install.sh and service units |
| Data defaults could use microSD paths | Explicit SSD paths, UUID/ext4/read-write guard, mount-bound services and RESCS per-request mount checking | deployment/pi/guard.py; RESCS mounts.py |
| Shared backend key did not bind a request to a profile | Expiring signed owner/method/path headers and updated RESCS 0.4 assertions | CORE-HOST/core/web/storage.py; RESCS gateway_scope.py |
| Owner administration needed no recent password check | Five-minute session-bound reauthentication, CSRF and failed-attempt throttling | CORE-HOST/core/web/accounts.py and gateway.py |
| Original browser had records but no complete file controls | Metadata/search, plain-text preview, upload/download, folders, read shares, Trash/restore/purge and quota controls | CORE-HOST/core/web/library.py and portal.html |
| Owner/full agents could inspect unrelated data through host tools | Pi profile uses tool-free assistance/code generation; full tool/coding execution blocked | CORE-HOST/core/web/services.py and chat_worker.py |
| Larger model/context defaults unsuitable for shared 8GB Pi | Explicit small Q4 tiers, 2048 context, reserve/peak/digest/device checks and explicit benchmark approvals | CORE-HOST/core/pi_resources.py and inference.py |
| Multiple providers could compete for inference | One CORE slot, bounded queue, shared root-owned flock used by updated ASCS, controlled model switching | CORE-HOST/core/web/services.py and ASCS deploy/pi |
| Pi coding UI could imply Build/Auto edits | Clear code-generation-only state; server rejects Build/Auto on Pi | CORE-HOST/core/web/services.py and portal.html |
| Optional native client treated queued as finished | Queued jobs remain active while polling; owner admin actions request password re-entry | CORE-CLIENT/client/desktop/app.py |
| Fresh Python environments mixed service minimum versions | Default Pi install needs Python 3.11; full ASCS remains a separate 3.12+ runtime | deployment/pi/rescs-requirements.txt; service pyprojects |
| Existing accounts/data lacked a coordinated migration path | Explicit preflight/copy utility with stopped-service checks, SQLite backup, separate-filesystem archive and rollback staging | deployment/pi/migrate.py |

The browser preview is bounded plain text. Folder grants are read-only; this is
not a general inherited-write ACL or filesystem synchronization engine. Trash is
logical CORE metadata over persistent RESCS bytes, and must be backed up with the
RESCS database/files. The administrator has account/quota controls but no private
content bypass. Root/OS compromise and client-side encryption remain separate.

New CORE APIs: POST /api/reauth; GET /api/ready; owner GET /api/ai-status;
GET/POST /api/folders; POST /api/shares; owner GET/POST /api/quotas; file
preview/move/trash/restore/purge routes. Legacy file delete moves to Trash.
Existing account IDs and namespace/owner/CAS record contracts are preserved.

Use the setup guide and VALIDATION.md for exact installation, backup, test and
rollback steps. Our Library/Day Quest are link integration only. ASIS/TIVISS
standalone source was retained; full Pi tools/voice/model quality are not certified.
