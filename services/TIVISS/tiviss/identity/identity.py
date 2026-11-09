"""Agent identity model.

The identity is a stable, explicit record of what this agent is. It is kept
separate from the model provider, conversation state, memory, and
configuration so the identity remains stable even if the underlying AI model
changes.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class IdentityValidationError(ValueError):
    """Raised when an agent identity is invalid."""


class IdentityState(StrEnum):
    """Lifecycle state of an agent identity."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    RETIRED = "retired"


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class AgentIdentity:
    """Immutable identity record for a T.I.V.I.S.S. agent.

    The agent ID is stable for the lifetime of the agent even if the name,
    model, or configuration changes.
    """

    agent_id: str
    name: str
    version: str
    state: IdentityState
    owner_id: str
    created_at: datetime
    meta: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        name: str,
        version: str,
        owner_id: str,
        agent_id: str | None = None,
        state: IdentityState | str = IdentityState.ACTIVE,
        created_at: datetime | None = None,
        meta: Mapping[str, Any] | None = None,
    ) -> AgentIdentity:
        """Create a validated identity.

        If ``agent_id`` is omitted a new UUID is generated. An explicit
        ``agent_id`` is allowed so ownership of the ID stays with the caller.
        """
        errors = cls.validate(
            name=name,
            version=version,
            owner_id=owner_id,
            agent_id=agent_id,
            state=state,
            created_at=created_at,
            meta=meta,
        )
        if errors:
            raise IdentityValidationError("; ".join(errors))

        try:
            state_value = (
                IdentityState(state) if not isinstance(state, IdentityState) else state
            )
        except ValueError as exc:  # pragma: no cover - guarded by validate()
            raise IdentityValidationError(f"unknown identity state: {state!r}") from exc

        return cls(
            agent_id=agent_id or str(uuid.uuid4()),
            name=name,
            version=version,
            state=state_value,
            owner_id=owner_id,
            created_at=created_at or utcnow(),
            meta=dict(meta or {}),
        )

    @staticmethod
    def validate(
        *,
        name: str,
        version: str,
        owner_id: str,
        agent_id: str | None,
        state: IdentityState | str,
        created_at: datetime | None,
        meta: Mapping[str, Any] | None,
    ) -> list[str]:
        """Return a list of validation errors (empty when valid)."""
        errors: list[str] = []
        if agent_id is not None and not (
            isinstance(agent_id, str) and agent_id.strip()
        ):
            errors.append("agent_id must be a non-empty string")
        if not (isinstance(name, str) and name.strip()):
            errors.append("name must be a non-empty string")
        if not (isinstance(version, str) and version.strip()):
            errors.append("version must be a non-empty string")
        if not (isinstance(owner_id, str) and owner_id.strip()):
            errors.append("owner_id must be a non-empty string")
        try:
            IdentityState(state)
        except (TypeError, ValueError):
            errors.append(f"state must be a valid IdentityState, got {state!r}")
        if created_at is not None:
            if not isinstance(created_at, datetime):
                errors.append("created_at must be a datetime")
            elif created_at.tzinfo is None or created_at.utcoffset() is None:
                errors.append("created_at must be timezone-aware")
        if meta is not None and not isinstance(meta, Mapping):
            errors.append("meta must be a mapping")
        return errors

    @staticmethod
    def validate_identity(identity: AgentIdentity) -> list[str]:
        """Validate an existing identity record."""
        return AgentIdentity.validate(
            name=identity.name,
            version=identity.version,
            owner_id=identity.owner_id,
            agent_id=identity.agent_id,
            state=identity.state,
            created_at=identity.created_at,
            meta=identity.meta,
        )
