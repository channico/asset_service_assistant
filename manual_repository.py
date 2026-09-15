"""Load and validate synthetic, versioned maintenance manuals."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from asset_repository import Asset


DEFAULT_MANUAL_DIRECTORY = Path(__file__).parent / "data" / "manuals"
VALID_VERSION_STATUSES = {"current", "superseded"}


def _require_text(record: dict[str, Any], fields: tuple[str, ...], kind: str) -> None:
    """Reject absent, empty, or non-text required fields."""
    for field in fields:
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{kind} field '{field}' must be a non-empty string")


@dataclass(frozen=True)
class ManualSection:
    """One independently retrievable section of a maintenance manual."""

    section_id: str
    title: str
    text: str

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "ManualSection":
        if not isinstance(record, dict):
            raise ValueError("Every manual section must be a JSON object")

        fields = ("section_id", "title", "text")
        _require_text(record, fields, "Manual section")
        return cls(**{field: record[field].strip() for field in fields})


@dataclass(frozen=True)
class MaintenanceManual:
    """A versioned manual that applies to one manufacturer and asset model."""

    manual_id: str
    title: str
    manufacturer: str
    applicable_model: str
    version: str
    version_status: str
    sections: tuple[ManualSection, ...]
    source_file: str

    @classmethod
    def from_dict(
        cls,
        record: dict[str, Any],
        source_file: str,
    ) -> "MaintenanceManual":
        if not isinstance(record, dict):
            raise ValueError("Each manual file must contain a JSON object")

        fields = (
            "manual_id",
            "title",
            "manufacturer",
            "applicable_model",
            "version",
            "version_status",
        )
        _require_text(record, fields, "Maintenance manual")

        version_status = record["version_status"].strip()
        if version_status not in VALID_VERSION_STATUSES:
            allowed = ", ".join(sorted(VALID_VERSION_STATUSES))
            raise ValueError(
                f"Unknown manual version status '{version_status}'. "
                f"Expected one of: {allowed}"
            )

        section_records = record.get("sections")
        if not isinstance(section_records, list) or not section_records:
            raise ValueError(
                "Maintenance manual field 'sections' must be a non-empty list"
            )

        sections = tuple(ManualSection.from_dict(item) for item in section_records)
        section_ids = [section.section_id.casefold() for section in sections]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("Every section_id within a manual must be unique")

        return cls(
            manual_id=record["manual_id"].strip(),
            title=record["title"].strip(),
            manufacturer=record["manufacturer"].strip(),
            applicable_model=record["applicable_model"].strip(),
            version=record["version"].strip(),
            version_status=version_status,
            sections=sections,
            source_file=source_file,
        )


def load_manuals(
    directory: Path = DEFAULT_MANUAL_DIRECTORY,
) -> list[MaintenanceManual]:
    """Load one manual from each JSON file in a directory."""
    paths = sorted(directory.glob("*.json"))
    if not paths:
        raise ValueError(f"No maintenance manual JSON files found in '{directory}'")

    manuals = []
    for path in paths:
        with path.open(encoding="utf-8") as file:
            record = json.load(file)
        manuals.append(MaintenanceManual.from_dict(record, path.name))

    manual_ids = [manual.manual_id.casefold() for manual in manuals]
    if len(manual_ids) != len(set(manual_ids)):
        raise ValueError("Every manual_id must be unique")

    return manuals


def validate_manual_applicability(
    manuals: list[MaintenanceManual],
    assets: list[Asset],
) -> None:
    """Ensure every manual applies to a manufacturer/model in the asset data."""
    asset_models = {
        (asset.manufacturer.casefold(), asset.model.casefold()) for asset in assets
    }
    missing_models = sorted(
        {
            f"{manual.manufacturer} {manual.applicable_model}"
            for manual in manuals
            if (
                manual.manufacturer.casefold(),
                manual.applicable_model.casefold(),
            )
            not in asset_models
        }
    )
    if missing_models:
        raise ValueError(
            "Manuals reference manufacturer/model pairs absent from the asset data: "
            + ", ".join(missing_models)
        )
