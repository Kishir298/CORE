"""
URL validation and SSRF protection for A.S.I.S. basic web access.

Every outbound web request (initial URL and each redirect hop) must pass
through :func:`validate_url` before connecting. Only ``http``/``https``
destinations that do not resolve to local/private/internal addresses are
permitted.

Web content retrieved through these helpers is untrusted external data;
callers must treat it as information only, never as instructions.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

ALLOWED_SCHEMES = frozenset({"http", "https"})

# Hostnames that always refer to the local machine.
_BLOCKED_HOSTNAMES = frozenset({"localhost"})

# IP ranges that must never be contacted (SSRF protection).
_BLOCKED_NETWORKS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("::ffff:0:0/96"),
)


class WebSecurityError(Exception):
    """Rejected or unresolvable web destination.

    ``code`` is a stable ``WEB_*`` category safe to surface to the model;
    ``message`` is already sanitized (no credentials, IPs, or paths).
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ValidatedURL:
    """A URL that passed scheme, shape, and SSRF checks."""

    url: str
    scheme: str
    host: str
    port: int


def is_blocked_ip(value: str) -> bool:
    """Return True when an IP literal falls inside a blocked network."""
    try:
        address = ipaddress.ip_address(value.strip().strip("[]"))
    except ValueError:
        return False
    return any(address in network for network in _BLOCKED_NETWORKS)


def _check_host_allowed(host: str) -> None:
    normalized = host.strip().lower().rstrip(".")
    if not normalized:
        raise WebSecurityError("WEB_INVALID_URL", "WEB_INVALID_URL: URL has no host.")
    if normalized in _BLOCKED_HOSTNAMES:
        raise WebSecurityError(
            "WEB_BLOCKED_DESTINATION",
            "WEB_BLOCKED_DESTINATION: local destinations are not permitted.",
        )
    if is_blocked_ip(normalized):
        raise WebSecurityError(
            "WEB_BLOCKED_DESTINATION",
            "WEB_BLOCKED_DESTINATION: private/internal destinations are not permitted.",
        )


def _check_resolved_addresses(host: str, port: int) -> None:
    """Resolve ``host`` and reject it when any address is non-public."""
    try:
        resolved = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise WebSecurityError(
            "WEB_UNAVAILABLE", "WEB_UNAVAILABLE: destination could not be resolved."
        ) from None
    except OSError:
        raise WebSecurityError(
            "WEB_UNAVAILABLE", "WEB_UNAVAILABLE: destination lookup failed."
        ) from None
    for _family, _kind, _proto, _canon, sockaddr in resolved:
        ip_text = sockaddr[0]
        try:
            address = ipaddress.ip_address(ip_text)
        except ValueError:
            raise WebSecurityError(
                "WEB_BLOCKED_DESTINATION",
                "WEB_BLOCKED_DESTINATION: destination address is not permitted.",
            ) from None
        # 0.0.0.0/:: (unspecified) must never be contacted either.
        if address.is_unspecified or any(
            address in network for network in _BLOCKED_NETWORKS
        ):
            raise WebSecurityError(
                "WEB_BLOCKED_DESTINATION",
                "WEB_BLOCKED_DESTINATION: private/internal destinations "
                "are not permitted.",
            )


def validate_url(url: str, *, max_url_length: int = 2000) -> ValidatedURL:
    """Validate a fetch/search URL and its resolved destination.

    Raises :class:`WebSecurityError` with a ``WEB_*`` code on any failure.
    """
    if not isinstance(url, str) or not url.strip():
        raise WebSecurityError(
            "WEB_INVALID_URL", "WEB_INVALID_URL: URL must be a non-empty string."
        )
    cleaned = url.strip()
    if "\x00" in cleaned:
        raise WebSecurityError("WEB_INVALID_URL", "WEB_INVALID_URL: malformed URL.")
    if len(cleaned) > max_url_length:
        raise WebSecurityError(
            "WEB_INVALID_URL",
            "WEB_INVALID_URL: URL exceeds the maximum permitted length.",
        )
    parsed = urlparse(cleaned)
    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        if not scheme:
            raise WebSecurityError(
                "WEB_INVALID_URL", "WEB_INVALID_URL: URL is malformed."
            )
        raise WebSecurityError(
            "WEB_UNSUPPORTED_SCHEME",
            "WEB_UNSUPPORTED_SCHEME: only http and https URLs are permitted.",
        )
    if parsed.username or parsed.password:
        raise WebSecurityError(
            "WEB_INVALID_URL", "WEB_INVALID_URL: URLs must not embed credentials."
        )
    host = parsed.hostname or ""
    _check_host_allowed(host)
    port = parsed.port or (443 if scheme == "https" else 80)
    _check_resolved_addresses(host, port)
    return ValidatedURL(url=cleaned, scheme=scheme, host=host, port=port)


def resolve_redirect(current_url: str, location: str) -> str:
    """Join a redirect ``Location`` against the current URL.

    The caller must pass the result through :func:`validate_url` again
    before following it, so redirect targets receive full SSRF checks.
    """
    if not isinstance(location, str) or not location.strip():
        raise WebSecurityError(
            "WEB_HTTP_ERROR", "WEB_HTTP_ERROR: redirect has no destination."
        )
    joined = urljoin(current_url, location.strip())
    if "\x00" in joined:
        raise WebSecurityError("WEB_INVALID_URL", "WEB_INVALID_URL: malformed URL.")
    return joined
