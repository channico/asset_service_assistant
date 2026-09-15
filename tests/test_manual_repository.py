import json
import tempfile
import unittest
from pathlib import Path

from asset_repository import load_assets
from manual_repository import (
    load_manuals,
    validate_manual_applicability,
)


def _manual_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "manual_id": "MAN-EXAMPLE-V1",
        "title": "Example Maintenance Guide",
        "manufacturer": "Ford",
        "applicable_model": "Transit",
        "version": "1.0",
        "version_status": "current",
        "sections": [
            {
                "section_id": "EXAMPLE-01",
                "title": "Example check",
                "text": "Record the observation and contact a qualified technician.",
            }
        ],
    }
    record.update(overrides)
    return record


def _write_manual(directory: Path, filename: str, record: object) -> None:
    (directory / filename).write_text(json.dumps(record), encoding="utf-8")


class ManualRepositoryTests(unittest.TestCase):
    def test_loads_versioned_manuals_with_structured_sections(self) -> None:
        manuals = load_manuals()

        self.assertGreaterEqual(len(manuals), 4)
        self.assertIn("current", {manual.version_status for manual in manuals})
        self.assertIn("superseded", {manual.version_status for manual in manuals})
        self.assertTrue(all(manual.sections for manual in manuals))
        self.assertTrue(
            all(
                section.section_id and section.title and section.text
                for manual in manuals
                for section in manual.sections
            )
        )

    @staticmethod
    def test_all_manuals_apply_to_a_stored_asset_model() -> None:
        validate_manual_applicability(load_manuals(), load_assets())

    def test_rejects_duplicate_manual_ids_ignoring_case(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            _write_manual(directory, "first.json", _manual_record())
            _write_manual(
                directory,
                "second.json",
                _manual_record(manual_id="man-example-v1", version="2.0"),
            )

            with self.assertRaisesRegex(ValueError, "manual_id must be unique"):
                load_manuals(directory)

    def test_rejects_invalid_version_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            _write_manual(
                directory,
                "manual.json",
                _manual_record(version_status="draft"),
            )

            with self.assertRaisesRegex(ValueError, "Unknown manual version status"):
                load_manuals(directory)

    def test_rejects_duplicate_section_ids_ignoring_case(self) -> None:
        sections = [
            {
                "section_id": "CHECK-01",
                "title": "First check",
                "text": "First passage.",
            },
            {
                "section_id": "check-01",
                "title": "Second check",
                "text": "Second passage.",
            },
        ]
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            _write_manual(
                directory,
                "manual.json",
                _manual_record(sections=sections),
            )

            with self.assertRaisesRegex(ValueError, "section_id.*unique"):
                load_manuals(directory)

    def test_rejects_section_with_blank_passage_text(self) -> None:
        sections = [
            {
                "section_id": "CHECK-01",
                "title": "Incomplete check",
                "text": "  ",
            }
        ]
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            _write_manual(
                directory,
                "manual.json",
                _manual_record(sections=sections),
            )

            with self.assertRaisesRegex(ValueError, "text.*non-empty string"):
                load_manuals(directory)

    def test_rejects_manual_for_unknown_asset_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            _write_manual(
                directory,
                "manual.json",
                _manual_record(applicable_model="Unknown Model"),
            )
            manuals = load_manuals(directory)
            assets = load_assets()

            with self.assertRaisesRegex(ValueError, "absent from the asset data"):
                validate_manual_applicability(manuals, assets)


if __name__ == "__main__":
    unittest.main()
