"""Shared Backwoods integration event envelope (transport-independent).

This module validates metadata only. Authentication, authorization, durable delivery,
tenant isolation and event persistence MUST be enforced by the receiving backend.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import UUID


class EventValidationError(ValueError):
    """Invalid shared integration event."""


@dataclass(frozen=True)
class IntegrationEvent:
    event_id: str
    event_type: str
    schema_version: int
    company_id: str
    entity_id: str
    actor_id: str
    occurred_at: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        try:
            UUID(self.event_id)
        except (ValueError, AttributeError, TypeError) as exc:
            raise EventValidationError("event_id must be a UUID") from exc
        for field in ("event_type", "company_id", "entity_id", "actor_id"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise EventValidationError(f"{field} must be a nonempty string")
        if not isinstance(self.schema_version, int) or isinstance(self.schema_version, bool) or self.schema_version < 1:
            raise EventValidationError("schema_version must be a positive integer")
        if not isinstance(self.payload, Mapping):
            raise EventValidationError("payload must be a mapping")
        try:
            dt = datetime.fromisoformat(self.occurred_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError, TypeError) as exc:
            raise EventValidationError("occurred_at must be ISO 8601") from exc
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise EventValidationError("occurred_at must include a timezone")

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "company_id": self.company_id,
            "entity_id": self.entity_id,
            "actor_id": self.actor_id,
            "occurred_at": self.occurred_at,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "IntegrationEvent":
        if not isinstance(data, Mapping):
            raise EventValidationError("event must be a mapping")
        try:
            return cls(**{key: data[key] for key in (
                "event_id", "event_type", "schema_version", "company_id",
                "entity_id", "actor_id", "occurred_at", "payload"
            )})
        except KeyError as exc:
            raise EventValidationError(f"missing field: {exc.args[0]}") from exc


def require_company(event: IntegrationEvent, authorized_company_id: str) -> None:
    """Fail closed if the event is not scoped to the authorized company."""
    if not authorized_company_id or event.company_id != authorized_company_id:
        raise PermissionError("event company does not match authorized company")
