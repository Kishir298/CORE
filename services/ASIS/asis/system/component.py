"""
Runtime component interface for A.S.I.S.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .context import RuntimeContext


class RuntimeComponent(ABC):
    """
    Base class for components managed by the A.S.I.S. runtime.

    Components contain their own startup and shutdown logic. The runtime
    starts them in registration order and stops them in reverse order.
    """

    name: str = "unnamed"

    @abstractmethod
    def start(self, context: RuntimeContext) -> None:
        """Start the component."""
        raise NotImplementedError

    @abstractmethod
    def stop(self, context: RuntimeContext) -> None:
        """Stop the component."""
        raise NotImplementedError
