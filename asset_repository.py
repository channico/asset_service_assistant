"""Load and query the synthetic asset records used in lesson 1."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_ASSET_FILE = Path(__file__).parent / "data" / "assets" / "assets.json"
VALID_STATUSES = {"active", "in_service", "out_of_service", "under_maintenance"}


@dataclass(frozen=True)
class Asset:
    """One maintainable vehicle or piece of equipment."""

    asset_id: str
    name: str
    asset_type: str
    manufacturer: str
    model: str
    year: int
    location: str
    status: str

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "Asset":
        """Validate a JSON object and turn it into an Asset."""
        required_text_fields = (
            "asset_id",
            "name",
            "asset_type",
            "manufacturer",
            "model",
            "location",
            "status",
        )

        for field in required_text_fields:
            value = record.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Asset field '{field}' must be a non-empty string")

        year = record.get("year")
        if not isinstance(year, int):
            raise ValueError("Asset field 'year' must be an integer")

        status = record["status"]
        if status not in VALID_STATUSES:
            allowed = ", ".join(sorted(VALID_STATUSES))
            raise ValueError(f"Unknown asset status '{status}'. Expected one of: {allowed}")

        return cls(
            asset_id=record["asset_id"],
            name=record["name"],
            asset_type=record["asset_type"],
            manufacturer=record["manufacturer"],
            model=record["model"],
            year=year,
            location=record["location"],
            status=status,
        )


def load_assets(path: Path = DEFAULT_ASSET_FILE) -> list[Asset]:
    """Load all assets from a JSON array."""
    with path.open(encoding="utf-8") as file:
        records = json.load(file)

    if not isinstance(records, list):
        raise ValueError("The asset data file must contain a JSON array")

    assets = [Asset.from_dict(record) for record in records]
    asset_ids = [asset.asset_id.upper() for asset in assets]
    if len(asset_ids) != len(set(asset_ids)):
        raise ValueError("Every asset_id must be unique")

    return assets


def find_asset(asset_id: str, assets: list[Asset]) -> Asset | None:
    """Return the asset with an exact ID match, ignoring letter case."""
    normalized_id = asset_id.strip().upper()
    return next(
        (asset for asset in assets if asset.asset_id.upper() == normalized_id),
        None,
    )
