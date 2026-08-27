from collections.abc import Callable
from threading import RLock

from core.errors import MessageError

from .models import Message


MessageHandler = Callable[[Message], Message | None]


class LocalCommunication:
    """
    In-process communication layer for C.O.R.E.

    LocalCommunication provides a concrete local transport used by C.O.R.E.
    Components communicate through named endpoints using standard Message
    objects.

    The transport is ready for use immediately after construction so the
    original v0.1 API remains backwards compatible. Explicit lifecycle
    methods are also provided for runtime orchestration.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, MessageHandler] = {}
        self._lock = RLock()

        # Local communication has historically been immediately usable.
        # Keep that behavior while still exposing explicit lifecycle control.
        self._active = True

        self._messages_sent = 0
        self._messages_received = 0

    def start(self) -> None:
        """Start the communication layer."""

        with self._lock:
            if self._active:
                return

            self._active = True

    def stop(self) -> None:
        """
        Stop the communication layer.

        Registered endpoints are retained so the transport can be restarted
        without requiring every component to register again.
        """

        with self._lock:
            self._active = False

    def register(
        self,
        endpoint: str,
        handler: MessageHandler,
    ) -> None:
        """Register a message handler for an endpoint."""

        if not endpoint:
            raise MessageError(
                "Communication endpoint cannot be empty."
            )

        if not callable(handler):
            raise MessageError(
                f"Handler for endpoint '{endpoint}' is not callable."
            )

        with self._lock:
            if endpoint in self._handlers:
                raise MessageError(
                    f"Endpoint already registered: {endpoint}"
                )

            self._handlers[endpoint] = handler

    def unregister(self, endpoint: str) -> None:
        """Remove a registered endpoint."""

        with self._lock:
            self._handlers.pop(endpoint, None)

    def send(self, message: Message) -> Message | None:
        """
        Send a message to its destination endpoint.

        The destination handler is executed synchronously and may return
        a response Message.
        """

        if not isinstance(message, Message):
            raise MessageError(
                "Communication can only send Message instances."
            )

        with self._lock:
            if not self._active:
                raise MessageError(
                    "Communication layer is not running."
                )

            handler = self._handlers.get(message.destination)

            if handler is None:
                raise MessageError(
                    f"Destination not registered: {message.destination}"
                )

            self._messages_sent += 1

        try:
            response = handler(message)
        except Exception as exc:
            raise MessageError(
                f"Message handling failed for destination: "
                f"{message.destination}"
            ) from exc

        with self._lock:
            self._messages_received += 1

        if response is not None and not isinstance(response, Message):
            raise MessageError(
                "Communication handlers must return a Message or None."
            )

        return response

    def request(
        self,
        source: str,
        destination: str,
        message_type: str,
        payload: dict | None = None,
    ) -> Message | None:
        """
        Create and send a request message.

        This provides a higher-level request API while keeping Message as
        the standard communication object.
        """

        message = Message(
            source=source,
            destination=destination,
            message_type=message_type,
            payload=payload or {},
        )

        return self.send(message)

    def has_endpoint(self, endpoint: str) -> bool:
        """Return whether an endpoint is registered."""

        with self._lock:
            return endpoint in self._handlers

    def endpoint_count(self) -> int:
        """Return the number of registered communication endpoints."""

        with self._lock:
            return len(self._handlers)

    def message_count(self) -> int:
        """Return the total number of successfully dispatched messages."""

        with self._lock:
            return self._messages_sent

    def response_count(self) -> int:
        """Return the number of completed handler dispatches."""

        with self._lock:
            return self._messages_received

    @property
    def is_running(self) -> bool:
        """Return whether the communication layer is active."""

        with self._lock:
            return self._active

    def clear(self) -> None:
        """
        Remove all registered communication endpoints.

        Communication counters are reset as well.
        """

        with self._lock:
            self._handlers.clear()
            self._messages_sent = 0
            self._messages_received = 0

    def count(self) -> int:
        """Return the number of registered communication endpoints."""

        return self.endpoint_count()