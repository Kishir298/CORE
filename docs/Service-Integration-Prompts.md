# Prompts for the other RISARMS service chats

Use each prompt with the current combined Pi ZIP and current service source. Each
chat should use the GitHub connector and preserve newer archive changes that are
not yet on GitHub. Require actual code, tests, an updated full package and a
setup/change document ready for risarms-docs. Never claim actual Pi hardware tests
without running on the device.

## ASIS

Use the GitHub connector to inspect ASIS and this combined CORE Pi release. Keep
member messaging tool-free and session/account-scoped. CORE currently uses its
central tool-free worker with per-account/service context, resource admission,
digest-bound approval, a shared inference queue/flock and 2048 context. Integrate
any replacement adapter with those contracts before enabling it; do not launch a
second uncoordinated provider. Keep Linux ARM64 supported features explicit and
full filesystem/voice/tools disabled where unvalidated. Avoid cloud fallback,
warmups and automatic model downloads. Retain standalone Windows/macOS/Linux
functionality and offline operation after preparation. Test cancellation, low RAM,
CPU pressure, history separation and model switching. Return full revised ASIS,
precise CORE adapter patches if needed, and setup/change documentation.

## ASCS

Use the GitHub connector and included updated ASCS Pi source. CORE's Pi portal
currently performs code generation with no tools, through its central scheduler;
standalone ASCS has its own protected Pi path and approval manifest. Both must use
/run/risarms-inference/queue.lock without double locking. Keep owner checks and
password re-entry at CORE, no unrelated private data or raw RESCS/host secrets,
no root/sudo/Docker socket, no arbitrary code execution without tested OS isolation.
Retain Python >=3.12 and standalone cross-platform behavior. Reconcile output,
context, timing and approval-policy differences explicitly; do not silently change
models or replay partial edits. Test direct engine bypass attempts, queue/cancel,
model identity and resource failures. Deliver full source, compatible patches,
validation and a setup/change document ready for risarms-docs.

## RESCS

Use the GitHub connector and included RESCS 0.4 source. Preserve signed expiring
owner/method/path assertions and the private SSD mount guard. CORE derives owner
from the verified session; explicit folder read grants are enforced by the gateway
before it signs the stored owner's scope. CORE owns folder/share/logical-Trash
metadata; RESCS owns hashes/bytes/records. Never bypass this through an admin role.
Reconcile quotas (8 MiB/file, CORE default 250 MiB/account, configurable up to the
Pi backend's 10 GiB ceiling). Preserve namespace/owner/CAS contracts and matching
backups; do not invent cross-backend transactions. Test actual API persistence,
disk-full/interrupted writes, expiry/replay scope, cross-user denial, restore/purge
and mount failures. Deliver the complete compatible source and change/setup guide.

## TIVISS

Use the GitHub connector and this Pi release. TIVISS execution is deliberately
blocked by CORE_SAFE_CHAT=1 until its ARM64 dependencies, isolation and resource
contracts are verified. Add an explicit supported code-generation-only or isolated
adapter if appropriate; never turn an owner role into access to other accounts.
Use the same inference lock/admission/context/model-digest policy and per-account
histories/workspaces. Retain standalone multi-OS offline functionality, with
network-only features reporting unavailable offline. No automatic cloud/model
fallback or action replay. Return revised source, exact integration patches,
validation and setup/change documentation ready for risarms-docs.
