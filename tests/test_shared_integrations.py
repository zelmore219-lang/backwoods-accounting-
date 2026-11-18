"""Standard-library tests: python -m unittest discover -s tests -p 'test_shared_integrations.py'"""
import unittest
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from shared_integrations.event_contract import IntegrationEvent, EventValidationError, require_company
from shared_integrations.timeclock import Punch, PunchKind, TimeclockError, validate_next, worked_seconds


class SharedIntegrationTests(unittest.TestCase):
    def test_event_roundtrip_and_company_guard(self):
        data = dict(event_id=str(uuid4()), event_type="fleet.vehicle.assigned",
                    schema_version=1, company_id="coffee", entity_id="van1",
                    actor_id="admin1", occurred_at="2026-11-17T23:00:00Z",
                    payload={"driver_id": "driver1"})
        event = IntegrationEvent.from_dict(data)
        self.assertEqual(event.as_dict(), data)
        require_company(event, "coffee")
        with self.assertRaises(PermissionError):
            require_company(event, "pest")
        with self.assertRaises(EventValidationError):
            IntegrationEvent.from_dict({**data, "occurred_at": "2026-11-17T23:00:00"})

    def test_cross_app_overnight_and_break(self):
        base = datetime(2026, 11, 17, 23, 0, tzinfo=timezone.utc)
        def punch(kind, mins, app):
            return Punch(str(uuid4()), "employee1", "coffee", "shift1",
                         kind, base + timedelta(minutes=mins), app, "tablet1")
        events = [punch(PunchKind.IN, 0, "warehouse"),
                  punch(PunchKind.BREAK_START, 60, "warehouse"),
                  punch(PunchKind.BREAK_END, 90, "driver"),
                  punch(PunchKind.OUT, 180, "driver")]
        for i, event in enumerate(events):
            validate_next(events[:i], event)
        self.assertEqual(worked_seconds(events), 150 * 60)
        with self.assertRaises(TimeclockError):
            validate_next(events, punch(PunchKind.OUT, 181, "driver"))

    def test_duplicate_and_overlap(self):
        now = datetime.now(timezone.utc)
        first = Punch("a", "e", "c", "s", PunchKind.IN, now, "fleet", "d")
        with self.assertRaises(TimeclockError):
            validate_next([first], first)
        second = Punch("b", "e", "c", "s2", PunchKind.IN, now + timedelta(minutes=1), "driver", "d")
        with self.assertRaises(TimeclockError):
            validate_next([first], second)


if __name__ == "__main__":
    unittest.main()
