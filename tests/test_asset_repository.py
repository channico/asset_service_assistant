import json
import tempfile
import unittest
from pathlib import Path

from asset_repository import find_asset, load_assets


class AssetRepositoryTests(unittest.TestCase):
    def test_loads_the_synthetic_assets(self) -> None:
        assets = load_assets()

        self.assertGreaterEqual(len(assets), 1)
        self.assertEqual(assets[0].asset_id, "VEH-1001")

    def test_finds_an_asset_by_exact_id(self) -> None:
        asset = find_asset("veh-1001", load_assets())

        self.assertIsNotNone(asset)
        self.assertEqual(asset.name, "North Service Van")

    def test_returns_none_for_an_unknown_id(self) -> None:
        asset = find_asset("VEH-9999", load_assets())

        self.assertIsNone(asset)

    def test_rejects_duplicate_asset_ids(self) -> None:
        duplicate_records = [
            {
                "asset_id": "EQP-1",
                "name": "First",
                "asset_type": "generator",
                "manufacturer": "Example",
                "model": "A",
                "year": 2024,
                "location": "Depot",
                "status": "active",
            },
            {
                "asset_id": "eqp-1",
                "name": "Second",
                "asset_type": "generator",
                "manufacturer": "Example",
                "model": "B",
                "year": 2025,
                "location": "Depot",
                "status": "active",
            },
        ]

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "assets.json"
            path.write_text(json.dumps(duplicate_records), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "asset_id must be unique"):
                load_assets(path)


if __name__ == "__main__":
    unittest.main()
