"""
Network detection for ASIS update system.

Provides fast, cached network availability detection with configurable
timeout to avoid blocking startup when offline.
"""

from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass, field

# requests is imported lazily in _requests()


@dataclass
class NetworkDetector:
    """
    Fast network availability detector with caching.

    Performs quick connectivity checks against reliable endpoints.
    Results are cached for the configured TTL to avoid repeated checks.
    """

    timeout: float = 3.0
    cache_ttl: float = 300.0  # 5 minutes
    _cached_result: bool | None = field(default=None, init=False)
    _cache_time: float = field(default=0.0, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    # Reliable endpoints for connectivity testing
    CHECK_ENDPOINTS = (
        ("dns", "8.8.8.8", 53),
        ("http_github", "https://github.com", 443),
        ("http_pypi", "https://pypi.org", 443),
    )

    def check(self, force: bool = False) -> bool:
        """
        Check network connectivity.

        Args:
            force: If True, bypass cache and perform fresh check.

        Returns:
            True if network appears available, False otherwise.
        """
        with self._lock:
            now = time.monotonic()
            if not force and self._cached_result is not None:
                if now - self._cache_time < self.cache_ttl:
                    return self._cached_result

            result = self._perform_check()
            self._cached_result = result
            self._cache_time = now
            return result

    def _perform_check(self) -> bool:
        """Perform actual connectivity checks."""
        # Quick DNS check first (fastest)
        if not self._check_dns():
            return False

        # HTTP checks with short timeout
        for name, host, port in self.CHECK_ENDPOINTS[1:]:
            if self._check_http(host):
                return True

        return False

    def _check_dns(self) -> bool:
        """Check DNS resolution."""
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=self.timeout)
            return True
        except (TimeoutError, OSError):
            return False

    def _requests(self):
        """Lazy import of requests."""
        try:
            import requests
            return requests
        except ImportError:
            return None

    def _check_http(self, url: str) -> bool:
        """Check HTTP connectivity to a host."""
        requests = self._requests()
        if requests is None:
            return False
        try:
            response = requests.head(
                url,
                timeout=self.timeout,
                allow_redirects=True,
                headers={"User-Agent": "ASIS-NetworkDetector/1.0"},
            )
            return response.status_code < 500
        except (requests.Timeout, requests.ConnectionError, requests.RequestException):
            return False
        except Exception:
            return False

    def invalidate_cache(self) -> None:
        """Force cache invalidation for next check."""
        with self._lock:
            self._cached_result = None
            self._cache_time = 0.0


# Global detector instance for convenience
_default_detector: NetworkDetector | None = None


def get_detector(
    timeout: float = 3.0,
    cache_ttl: float = 300.0,
) -> NetworkDetector:
    """Get or create the global network detector."""
    global _default_detector
    if _default_detector is None:
        _default_detector = NetworkDetector(timeout=timeout, cache_ttl=cache_ttl)
    return _default_detector


def is_online(timeout: float = 3.0, force: bool = False) -> bool:
    """
    Convenience function to check if network is available.

    Args:
        timeout: Connection timeout in seconds.
        force: Force fresh check, bypassing cache.

    Returns:
        True if online, False if offline or check failed.
    """
    detector = get_detector(timeout=timeout)
    return detector.check(force=force)


def set_online_status(status: bool) -> None:
    """Manually override online status (for testing)."""
    global _default_detector
    if _default_detector is not None:
        with _default_detector._lock:
            _default_detector._cached_result = status
            _default_detector._cache_time = time.monotonic()
