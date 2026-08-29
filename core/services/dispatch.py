from collections.abc import Callable
from typing import Any

from core.communication import Message
from core.services.manager import ServiceManager
from core.services.models import ServiceRequest, ServiceResponse

EventEmitter = Callable[[str, str, dict], None]

SERVICE_ENDPOINT_PREFIX = "service:"

OPERATION_KEY = "operation"


class ServiceDispatcher:
    """
    Bridges routed messages to service operation execution.

    A service endpoint is registered on the communication transport for
    each C.O.R.E. service. When a message is routed to that endpoint,
    ServiceDispatcher converts it into a ServiceRequest, executes the
    requested operation through ServiceManager, and converts the result
    back into a response message.

    This completes the canonical flow:
        Message -> Router -> Destination -> Service -> Operation -> Response
    """

    def __init__(
        self,
        services: ServiceManager,
        emitter: EventEmitter | None = None,
    ) -> None:
        self._services = services
        self._emitter = emitter

    def endpoint_for(self, service_id: str) -> str:
        """Return the transport endpoint that dispatches to a service."""

        return f"{SERVICE_ENDPOINT_PREFIX}{service_id}"

    def is_service_endpoint(self, destination: str) -> bool:
        """Return whether a destination is a service endpoint."""

        return destination.startswith(SERVICE_ENDPOINT_PREFIX)

    def service_id_for(self, destination: str) -> str:
        """Extract the service id from a service endpoint."""

        return destination[len(SERVICE_ENDPOINT_PREFIX):]

    def to_request(self, message: Message) -> ServiceRequest:
        """Convert a routed message into a service request."""

        service_id = self.service_id_for(message.destination)

        operation = message.payload.get(OPERATION_KEY)

        if not operation or not isinstance(operation, str):
            raise ValueError(
                "Service message payload must declare a string "
                f"'{OPERATION_KEY}'."
            )

        arguments = {
            key: value
            for key, value in message.payload.items()
            if key != OPERATION_KEY
        }

        return ServiceRequest(
            service_id=service_id,
            operation=operation,
            payload=arguments,
            request_id=message.request_id or message.message_id,
        )

    def dispatch(self, request: ServiceRequest) -> ServiceResponse:
        """
        Execute a service operation and return a response.

        Operation handlers are responsible for interpreting request payload
        values. Successful execution returns success=True; failures are
        captured as error responses rather than exceptions so a response
        can always be delivered back through the routing spine.
        """

        try:
            result = self._services.execute(
                request.service_id,
                request.operation,
                **request.payload,
            )
        except Exception as exc:
            if self._emitter is not None:
                self._emitter(
                    "SERVICE_FAILED",
                    f"service:{request.service_id}",
                    {
                        "service_id": request.service_id,
                        "operation": request.operation,
                        "error": str(exc),
                    },
                )

            return ServiceResponse(
                service_id=request.service_id,
                operation=request.operation,
                success=False,
                request_id=request.request_id,
                error=str(exc),
            )

        if self._emitter is not None:
            self._emitter(
                "SERVICE_EXECUTED",
                f"service:{request.service_id}",
                {
                    "service_id": request.service_id,
                    "operation": request.operation,
                },
            )

        return ServiceResponse(
            service_id=request.service_id,
            operation=request.operation,
            payload=_coerce_payload(result),
            success=True,
            request_id=request.request_id,
        )

    def to_message(
        self,
        response: ServiceResponse,
        source: str,
    ) -> Message:
        """Build a response message linking the original request."""

        return Message(
            source=source,
            destination="router",
            message_type="SERVICE_RESPONSE",
            payload={
                "service_id": response.service_id,
                "operation": response.operation,
                "result": response.payload,
                "success": response.success,
                "error": response.error,
            },
            request_id=response.request_id,
        )

    def handle(self, message: Message) -> Message:
        """
        Transport endpoint handler: process a routed service message.

        Invalid requests are converted into error responses so the routing
        spine always delivers a structured result back to the caller.
        """

        if not isinstance(message.payload, dict):
            response = ServiceResponse(
                service_id=self.service_id_for(message.destination),
                operation="",
                success=False,
                request_id=message.request_id or message.message_id,
                error="Service message payload must be a dictionary.",
            )
            return self.to_message(response, source=message.destination)

        try:
            request = self.to_request(message)
        except ValueError as exc:
            response = ServiceResponse(
                service_id=self.service_id_for(message.destination),
                operation="",
                success=False,
                request_id=message.request_id or message.message_id,
                error=str(exc),
            )
            return self.to_message(response, source=message.destination)

        response = self.dispatch(request)
        return self.to_message(response, source=message.destination)


def _coerce_payload(result: Any) -> dict[str, Any]:
    """Wrap an operation result into a serializable payload."""

    if isinstance(result, dict):
        return result

    return {"value": result}
