import json
import unittest
from unittest.mock import patch

from asset_repository import DEFAULT_ASSET_FILE
from asset_tools import (
    find_similar_incidents,
    get_asset_details,
    get_maintenance_history,
    get_ticket,
)
from service_repository import DEFAULT_MAINTENANCE_FILE, DEFAULT_TICKET_FILE


class AssetDetailsToolTests(unittest.TestCase):
    def test_valid_id_returns_the_exact_stored_record(self) -> None:
        stored_records = json.loads(DEFAULT_ASSET_FILE.read_text(encoding="utf-8"))
        expected = next(
            record for record in stored_records if record["asset_id"] == "VEH-1001"
        )

        result = get_asset_details("veh-1001")

        self.assertEqual(result["status"], "found")
        self.assertEqual(result["asset"], expected)
        self.assertIsNone(result["error"])

    def test_unknown_id_returns_a_structured_not_found_result(self) -> None:
        result = get_asset_details("VEH-9999")

        self.assertEqual(
            result,
            {
                "status": "not_found",
                "asset": None,
                "error": {
                    "code": "asset_not_found",
                    "message": "No asset found with exact ID 'VEH-9999'.",
                },
            },
        )

    def test_malformed_text_id_returns_not_found(self) -> None:
        result = get_asset_details("VEH-100")

        self.assertEqual(result["status"], "not_found")
        self.assertIsNone(result["asset"])
        self.assertEqual(result["error"]["code"], "malformed_asset_id")

    def test_non_text_id_returns_not_found(self) -> None:
        result = get_asset_details(None)

        self.assertEqual(result["status"], "not_found")
        self.assertIsNone(result["asset"])
        self.assertEqual(result["error"]["code"], "malformed_asset_id")

    def test_near_match_does_not_return_an_asset(self) -> None:
        result = get_asset_details("VEH-1004")

        self.assertEqual(result["status"], "not_found")
        self.assertIsNone(result["asset"])


class MaintenanceHistoryToolTests(unittest.TestCase):
    def test_returns_only_requested_asset_events_newest_first(self) -> None:
        result = get_maintenance_history(" veh-1001 ")

        self.assertEqual(result["status"], "found")
        self.assertEqual(result["asset_id"], "VEH-1001")
        self.assertTrue(result["events"])
        self.assertTrue(
            all(event["asset_id"] == "VEH-1001" for event in result["events"])
        )
        self.assertEqual(
            [event["service_date"] for event in result["events"]],
            ["2026-06-11", "2026-01-12"],
        )
        self.assertEqual(result["returned_count"], 2)
        self.assertEqual(result["total_count"], 2)

    def test_limit_returns_only_the_newest_events(self) -> None:
        stored_events = json.loads(
            DEFAULT_MAINTENANCE_FILE.read_text(encoding="utf-8")
        )
        newest = max(
            (
                event
                for event in stored_events
                if event["asset_id"] == "VEH-1001"
            ),
            key=lambda event: (event["service_date"], event["maintenance_id"]),
        )

        result = get_maintenance_history("VEH-1001", limit=1)

        self.assertEqual(result["events"], [newest])
        self.assertEqual(result["returned_count"], 1)
        self.assertEqual(result["total_count"], 2)

    def test_known_asset_without_history_returns_explained_empty_result(self) -> None:
        with patch("asset_tools.load_maintenance_events", return_value=[]):
            result = get_maintenance_history("VEH-1001")

        self.assertEqual(result["status"], "found")
        self.assertEqual(result["events"], [])
        self.assertEqual(result["returned_count"], 0)
        self.assertEqual(result["total_count"], 0)
        self.assertEqual(
            result["explanation"],
            "No maintenance history recorded for asset 'VEH-1001'.",
        )
        self.assertIsNone(result["error"])

    def test_unknown_asset_does_not_return_history(self) -> None:
        result = get_maintenance_history("VEH-9999")

        self.assertEqual(result["status"], "not_found")
        self.assertEqual(result["events"], [])
        self.assertEqual(result["error"]["code"], "asset_not_found")

    def test_invalid_limit_returns_a_structured_error(self) -> None:
        for invalid_limit in (0, -1, 1.5, "2", True):
            with self.subTest(limit=invalid_limit):
                result = get_maintenance_history(
                    "VEH-1001", limit=invalid_limit
                )

                self.assertEqual(result["status"], "invalid_request")
                self.assertEqual(result["events"], [])
                self.assertEqual(result["error"]["code"], "invalid_limit")


class TicketLookupToolTests(unittest.TestCase):
    def test_exact_ticket_lookup_returns_stored_record(self) -> None:
        stored_records = json.loads(DEFAULT_TICKET_FILE.read_text(encoding="utf-8"))
        expected = next(
            record for record in stored_records if record["ticket_id"] == "TKT-0001"
        )

        result = get_ticket(" tkt-0001 ")

        self.assertEqual(result["status"], "found")
        self.assertEqual(result["match_type"], "exact_ticket")
        self.assertEqual(result["ticket"], expected)
        self.assertIsNone(result["error"])

    def test_unknown_ticket_returns_structured_not_found_result(self) -> None:
        result = get_ticket("TKT-9999")

        self.assertEqual(result["status"], "not_found")
        self.assertEqual(result["match_type"], "exact_ticket")
        self.assertIsNone(result["ticket"])
        self.assertEqual(result["error"]["code"], "ticket_not_found")

    def test_malformed_ticket_id_does_not_use_near_matching(self) -> None:
        result = get_ticket("TKT-001")

        self.assertEqual(result["status"], "not_found")
        self.assertEqual(result["error"]["code"], "malformed_ticket_id")


class SimilarIncidentToolTests(unittest.TestCase):
    def test_related_incident_exposes_matching_evidence(self) -> None:
        result = find_similar_incidents(
            "VEH-1001", "The sliding door is difficult to close"
        )

        self.assertEqual(result["status"], "found")
        self.assertEqual(result["asset_model"], "Transit")
        self.assertEqual(result["returned_count"], 1)
        incident = result["incidents"][0]
        self.assertEqual(incident["match_type"], "related_incident")
        self.assertEqual(incident["ticket"]["ticket_id"], "TKT-0001")
        self.assertEqual(
            incident["evidence"]["matched_symptom_tags"],
            ["sliding", "door", "close"],
        )
        self.assertIn("do not prove", result["disclaimer"])

    def test_open_ticket_is_not_returned_as_closed_incident(self) -> None:
        result = find_similar_incidents(
            "VEH-1003", "The compartment light does not illuminate"
        )

        self.assertEqual(result["status"], "found")
        self.assertEqual(result["incidents"], [])
        self.assertEqual(result["returned_count"], 0)
        self.assertIsNotNone(result["explanation"])

    def test_unknown_asset_returns_structured_not_found_result(self) -> None:
        result = find_similar_incidents("VEH-9999", "door will not close")

        self.assertEqual(result["status"], "not_found")
        self.assertEqual(result["incidents"], [])
        self.assertEqual(result["error"]["code"], "asset_not_found")

    def test_blank_symptom_returns_structured_invalid_request(self) -> None:
        result = find_similar_incidents("VEH-1001", "  ")

        self.assertEqual(result["status"], "invalid_request")
        self.assertEqual(result["incidents"], [])
        self.assertEqual(result["error"]["code"], "invalid_symptom")


if __name__ == "__main__":
    unittest.main()
