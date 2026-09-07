# Physical LAN Readiness — Windows host ↔ Mac device

## Status

```text
AUTOMATED TESTING:      IMPLEMENTED (localhost suites, all passing)
PHYSICAL LAN VALIDATION: NOT YET PERFORMED — do not claim otherwise
```

The physical test has NOT been run. This document is the procedure for
when the user performs it.

## Topology under test

```text
WINDOWS (C.O.R.E. host/server)
    │ real LAN TCP/TLS
    ▼
MAC (external R.I.S.A.R.M.S. device)
```

## Windows host preparation

1. Add the firewall exception (`docs/windows-firewall.md`) for the
   configured port (example below uses `5000`).
2. Provide a server TLS certificate (external `0.0.0.0` binding fails
   closed without valid TLS 1.2+ material — never disable this).
3. Configure `config/core.yaml` (or `CORE_*` environment overrides):

```yaml
communication:
  enabled: true
  transport: tcp
  host: "0.0.0.0"
  port: 5000
  tls:
    enabled: true
    certfile: "C:\\path\\to\\core.crt"
    keyfile: "C:\\path\\to\\core.key"

network:
  enabled: true

security:
  provider: token

rescs:
  adapter: file
  path: "var/rescs.json"
```

4. Ensure the Mac's identity exists on first connect: either pre-register
   it (`security` identity with `device` type + token) or let the first
   authenticated registration persist it automatically (token is captured
   from the provisioned identity at registration time).
5. Start C.O.R.E.: `py -m core --config config/core.yaml start`.

## Expected first-registration sequence (Mac)

```text
TCP connect to <windows-lan-ip>:5000
TLS handshake (1.2+)
CORE_HANDSHAKE {identity_id, credential, protocol_version: "0.3.0"}
CORE_HANDSHAKE_RESPONSE {authenticated: true, ...}
DEVICE_REGISTER {device_id, device_name, device_type, platform, capabilities, protocol_version}
DEVICE_REGISTER_RESPONSE {registered: true, device_id, status: "online"}
```

On the host, `var/rescs.json` must gain a `devices` entry for the Mac
(identity fields + token; no `connection_id`, no live status).

## Expected disconnect behavior

Mac disconnects (or loses Wi-Fi / shuts down): host marks it `offline`,
clears `connection_id`, updates `last_seen`. The `devices` entry remains.

## Expected restart behavior

Shut C.O.R.E. down and start it again **before** the Mac reconnects:

- log shows the restore count (`Restored N persisted device(s)`)
- discovery lists the Mac as `status: offline`
- `registered_devices` includes it; `online_devices` does not

## Expected reconnect behavior

Mac reconnects with the same `device_id`/`identity_id` + credential:

- authentication succeeds against the re-provisioned identity
- `DEVICE_REGISTER` restores the same logical record, `online`, with a
  NEW `connection_id`
- counts read `registered=1, online=1, offline=0` for a single device
- duplicate `DEVICE_REGISTER` while online is rejected with
  `DEVICE_ALREADY_REGISTERED`; a wrong credential is rejected and the
  device stays `offline`

## Validation checklist (fill in during the physical test)

- [ ] TLS handshake succeeds from Mac to Windows
- [ ] `CORE_HANDSHAKE_RESPONSE.authenticated == true`
- [ ] First `DEVICE_REGISTER` returns `status: online`
- [ ] `var/rescs.json` contains the Mac identity (no connection state)
- [ ] Mac Wi-Fi drop → host shows `offline`, record retained
- [ ] C.O.R.E. restart → Mac restored as `offline`
- [ ] Mac reconnect → `online`, same `device_id`, new `connection_id`
- [ ] Wrong credential → rejected, stays `offline`
- [ ] Claiming another `device_id` → rejected

## Security notes

- Never disable TLS or switch to the existence provider for the LAN test.
- `var/rescs.json` contains device tokens: it is git-ignored local state;
  never commit it, never copy it off the host insecurely.
