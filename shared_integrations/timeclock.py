"""Pure shared time-clock rules; no database or authentication side effects.

The authoritative Employee backend must authenticate PINs, serialize writes per
employee/company, persist punches and audit changes transactionally.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable


class PunchKind(str, Enum):
    IN = "in"
    OUT = "out"
    BREAK_START = "break_start"
    BREAK_END = "break_end"


class TimeclockError(ValueError):
    pass


@dataclass(frozen=True)
class Punch:
    punch_id: str
    employee_id: str
    company_id: str
    shift_id: str
    kind: PunchKind
    occurred_at: datetime
    source_app: str
    device_id: str

    def __post_init__(self) -> None:
        for name in ("punch_id", "employee_id", "company_id", "shift_id", "source_app", "device_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise TimeclockError(f"{name} is required")
        if not isinstance(self.kind, PunchKind):
            raise TimeclockError("unknown punch kind")
        if not isinstance(self.occurred_at, datetime) or self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise TimeclockError("punch timestamp must be timezone-aware")


def validate_next(history: Iterable[Punch], candidate: Punch) -> None:
    """Validate transitions; call inside an authoritative serialized transaction.

    Duplicate punch IDs are idempotent only if the stored punch is identical.
    This function rejects duplicates; the persistence adapter must return the
    original result for a matching ID instead of inserting it again.
    """
    records = list(history)
    for old in records:
        if old.punch_id == candidate.punch_id:
            raise TimeclockError("duplicate punch ID: check existing result")
        if old.employee_id != candidate.employee_id or old.company_id != candidate.company_id:
            raise TimeclockError("mixed employee or company punch history")
    ordered = sorted(records, key=lambda p: p.occurred_at)
    if ordered and candidate.occurred_at <= ordered[-1].occurred_at:
        raise TimeclockError("punch must be later than the previous punch")
    state = "off"
    current_shift = None
    for punch in ordered + [candidate]:
        if punch.kind is PunchKind.IN:
            if state != "off":
                raise TimeclockError("already clocked in")
            state, current_shift = "working", punch.shift_id
        elif punch.kind is PunchKind.BREAK_START:
            if state != "working" or punch.shift_id != current_shift:
                raise TimeclockError("cannot start break")
            state = "break"
        elif punch.kind is PunchKind.BREAK_END:
            if state != "break" or punch.shift_id != current_shift:
                raise TimeclockError("cannot end break")
            state = "working"
        elif punch.kind is PunchKind.OUT:
            if state != "working" or punch.shift_id != current_shift:
                raise TimeclockError("cannot clock out")
            state, current_shift = "off", None


def worked_seconds(history: Iterable[Punch]) -> int:
    """Return completed working intervals, excluding breaks and open shifts.

    This is a raw duration helper, NOT payroll-ready hours or overtime policy.
    """
    ordered = sorted(history, key=lambda p: p.occurred_at)
    if not ordered:
        return 0
    total = 0
    active_since = None
    for punch in ordered:
        if punch.kind in (PunchKind.IN, PunchKind.BREAK_END):
            active_since = punch.occurred_at
        elif punch.kind in (PunchKind.BREAK_START, PunchKind.OUT):
            if active_since is not None:
                total += int((punch.occurred_at - active_since).total_seconds())
            active_since = None
    return total
