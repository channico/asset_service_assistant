import json
import unittest

from asset_repository import DEFAULT_ASSET_FILE
from asset_tools import get_asset_details


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


if __name__ == "__main__":
    unittest.main()
