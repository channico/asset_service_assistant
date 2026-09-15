"""Deterministic tools for retrieving authoritative asset records."""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from asset_repository import find_asset, load_assets
from service_repository import load_maintenance_events


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


def get_maintenance_history(
    asset_id: object,
    limit: object = None,
) -> dict[str, Any]:
    """Return one known asset's maintenance events, newest first.

    The asset ID follows the same exact-match rules as ``get_asset_details``.
    ``limit`` may be omitted or set to a positive integer.
    """
    asset_result = get_asset_details(asset_id)
    if asset_result["status"] == "not_found":
        return {
            "status": "not_found",
            "asset_id": None,
            "events": [],
            "returned_count": 0,
            "total_count": 0,
            "explanation": None,
            "error": asset_result["error"],
        }

    if isinstance(limit, bool) or (
        limit is not None and (not isinstance(limit, int) or limit < 1)
    ):
        return {
            "status": "invalid_request",
            "asset_id": asset_result["asset"]["asset_id"],
            "events": [],
            "returned_count": 0,
            "total_count": 0,
            "explanation": None,
            "error": {
                "code": "invalid_limit",
                "message": "Limit must be a positive integer or omitted.",
            },
        }

    normalized_id = asset_result["asset"]["asset_id"]
    matching_events = [
        event
        for event in load_maintenance_events()
        if event.asset_id.upper() == normalized_id.upper()
    ]
    matching_events.sort(
        key=lambda event: (event.service_date, event.maintenance_id.upper()),
        reverse=True,
    )

    total_count = len(matching_events)
    if limit is not None:
        matching_events = matching_events[:limit]

    explanation = None
    if total_count == 0:
        explanation = f"No maintenance history recorded for asset '{normalized_id}'."

    return {
        "status": "found",
        "asset_id": normalized_id,
        "events": [asdict(event) for event in matching_events],
        "returned_count": len(matching_events),
        "total_count": total_count,
        "explanation": explanation,
        "error": None,
    }
