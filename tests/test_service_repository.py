import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from asset_repository import load_assets
from service_repository import (
    DEFAULT_MAINTENANCE_FILE,
    DEFAULT_TICKET_FILE,
    load_maintenance_events,
    load_service_tickets,
    validate_asset_references,
)


class ServiceRepositoryTests(unittest.TestCase):
    def test_dataset_meets_minimum_record_counts(self) -> None:
        self.assertGreaterEqual(len(load_assets()), 10)
        self.assertGreaterEqual(len(load_maintenance_events()), 15)
        self.assertGreaterEqual(len(load_service_tickets()), 10)

    @staticmethod
    def test_all_records_reference_known_assets() -> None:
        validate_asset_references(
            load_assets(), load_maintenance_events(), load_service_tickets()
        )

    def test_rejects_duplicate_maintenance_ids(self) -> None:
        records = json.loads(DEFAULT_MAINTENANCE_FILE.read_text(encoding="utf-8"))
        duplicate = records[0].copy()
        duplicate["maintenance_id"] = records[0]["maintenance_id"].lower()
        records.append(duplicate)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "maintenance_events.json"
            path.write_text(json.dumps(records), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "maintenance_id must be unique"):
                load_maintenance_events(path)

    def test_rejects_missing_ticket_id(self) -> None:
        records = json.loads(DEFAULT_TICKET_FILE.read_text(encoding="utf-8"))
        records[0].pop("ticket_id")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "service_tickets.json"
            path.write_text(json.dumps(records), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "ticket_id.*non-empty string"):
                load_service_tickets(path)

    def test_rejects_invalid_symptom_tags(self) -> None:
        records = json.loads(DEFAULT_TICKET_FILE.read_text(encoding="utf-8"))
        records[0]["symptom_tags"] = ["door", "DOOR"]

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "service_tickets.json"
            path.write_text(json.dumps(records), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "symptom tags must be unique"):
                load_service_tickets(path)

    def test_rejects_reference_to_unknown_asset(self) -> None:
        assets = load_assets()
        events = load_maintenance_events()
        tickets = load_service_tickets()
        events[0] = replace(events[0], asset_id="MISSING-9999")

        with self.assertRaisesRegex(ValueError, "missing asset IDs"):
            validate_asset_references(assets, events, tickets)


if __name__ == "__main__":
    unittest.main()
