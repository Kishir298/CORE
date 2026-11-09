"""
Interrupt coordination for A.S.I.S.

In-flight operations register a cancellation token under a named scope
("inference", "voice", "tools"). A request to cancel marks the token;
long-running code periodically calls ``check`` and aborts. Cancellation
is cooperative and thread-safe, mirroring how a future C.O.R.E.
lifecycle adapter will control A.S.I.S.
"""

from __future__ import annotations

import threading

from asis.errors import CancellationError


class CancellationToken:
    """Thread-safe cooperative cancellation flag."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def reset(self) -> None:
        self._event.clear()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        """Raise CancellationError when cancellation was requested."""
        if self._event.is_set():
            raise CancellationError("Operation cancelled.")


class InterruptCoordinator:
    """Manages cancellation tokens for named operation scopes."""

    def __init__(self) -> None:
        self._tokens: dict[str, CancellationToken] = {}
        self._lock = threading.RLock()

    def register(self, scope: str) -> CancellationToken:
        """Return the cancellation token for a scope, creating if needed."""
        with self._lock:
            token = self._tokens.get(scope)

            if token is None:
                token = CancellationToken()
                self._tokens[scope] = token

            token.reset()
            return token

    def cancel(self, scope: str) -> bool:
        """Cancel a scope. Returns True if a token existed."""
        with self._lock:
            token = self._tokens.get(scope)

            if token is None:
                return False

            token.cancel()
            return True

    def is_cancelled(self, scope: str) -> bool:
        with self._lock:
            token = self._tokens.get(scope)
            return token.cancelled if token is not None else False

    def check(self, scope: str) -> None:
        """Raise CancellationError if the scope was cancelled."""
        with self._lock:
            token = self._tokens.get(scope)

        if token is not None:
            token.check()

    def cancel_all(self) -> None:
        """Cancel every registered scope."""
        with self._lock:
            scopes = list(self._tokens)

        for scope in scopes:
            self.cancel(scope)

    def clear(self) -> None:
        """Drop all tokens."""
        with self._lock:
            self._tokens.clear()
