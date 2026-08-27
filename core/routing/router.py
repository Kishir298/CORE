from core.communication import LocalCommunication, Message
from core.errors import RoutingError


class Router:
    """Routes C.O.R.E. messages to registered destinations."""

    def __init__(self, communication: LocalCommunication) -> None:
        self._communication = communication
        self._routes: dict[str, str] = {}

    def add_route(self, message_type: str, destination: str) -> None:
        """Route a message type to a destination."""

        self._routes[message_type] = destination

    def remove_route(self, message_type: str) -> None:
        """Remove a message-type route."""

        self._routes.pop(message_type, None)

    def get_route(self, message_type: str) -> str:
        """Return the destination for a message type."""

        try:
            return self._routes[message_type]
        except KeyError as exc:
            raise RoutingError(
                f"No route configured for message type: {message_type}"
            ) from exc

    def route(self, message: Message) -> Message | None:
        """Route a message to its configured destination."""

        destination = self.get_route(message.message_type)

        routed_message = Message(
            source=message.source,
            destination=destination,
            message_type=message.message_type,
            payload=message.payload,
            message_id=message.message_id,
            timestamp=message.timestamp,
            request_id=message.request_id,
        )

        try:
            return self._communication.send(routed_message)
        except Exception as exc:
            if isinstance(exc, RoutingError):
                raise

            raise RoutingError(
                f"Failed to route message to: {destination}"
            ) from exc

    def clear(self) -> None:
        """Remove all configured routes."""

        self._routes.clear()

    def count(self) -> int:
        return len(self._routes)
