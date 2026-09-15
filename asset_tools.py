"""Deterministic tools for retrieving authoritative asset records."""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from asset_repository import find_asset, load_assets


ASSET_ID_PATTERN = re.compile(r"[A-Z]{3}-\d{4}")


def _not_found(code: str, message: str) -> dict[str, Any]:
    """Build the stable not-found response used by asset lookup tools."""
    return {
        "status": "not_found",
        "asset": None,
        "error": {
            "code": code,
            "message": message,
        },
    }


def get_asset_details(asset_id: object) -> dict[str, Any]:
    """Return the stored record for one exact asset ID.

    Matching is deterministic and case-insensitive. It does not use fuzzy or
    semantic similarity, so a near match is treated as not found.
    """
    if not isinstance(asset_id, str):
        return _not_found(
            "malformed_asset_id",
            "Asset ID must be text in the format ABC-1234.",
        )

    normalized_id = asset_id.strip().upper()
    if ASSET_ID_PATTERN.fullmatch(normalized_id) is None:
        return _not_found(
            "malformed_asset_id",
            "Asset ID must be text in the format ABC-1234.",
        )

    asset = find_asset(normalized_id, load_assets())
    if asset is None:
        return _not_found(
            "asset_not_found",
            f"No asset found with exact ID '{normalized_id}'.",
        )

    return {
        "status": "found",
        "asset": asdict(asset),
        "error": None,
    }
