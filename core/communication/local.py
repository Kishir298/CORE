from collections import defaultdict
from collections.abc import Callable

from core.errors import MessageError

from .models import Message


MessageHandler = Callable[[Message], Message | None]


class LocalCommunication:
    """In-process communication layer for C.O.R.E."""

    def __init__(self) -> None:
        self._handlers: dict[str, MessageHandler] = {}

    def register(
        self,
        endpoint: str,
        handler: MessageHandler,
    ) -> None:
        if endpoint in self._handlers:
            raise MessageError(
                f"Endpoint already registered: {endpoint}"
            )

        self._handlers[endpoint] = handler

    def unregister(self, endpoint: str) -> None:
        self._handlers.pop(endpoint, None)

    def send(self, message: Message) -> Message | None:
        handler = self._handlers.get(message.destination)

        if handler is None:
            raise MessageError(
                f"Destination not registered: {message.destination}"
            )

        return handler(message)

    def has_endpoint(self, endpoint: str) -> bool:
        return endpoint in self._handlers

    def endpoint_count(self) -> int:
        return len(self._handlers)
