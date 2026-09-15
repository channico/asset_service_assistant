"""Deterministic tools for retrieving authoritative asset records."""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from asset_repository import find_asset, load_assets
from service_repository import load_maintenance_events, load_service_tickets


ASSET_ID_PATTERN = re.compile(r"[A-Z]{3}-\d{4}")
TICKET_ID_PATTERN = re.compile(r"TKT-\d{4}")


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


def _ticket_not_found(code: str, message: str) -> dict[str, Any]:
    """Build the stable not-found response used by exact ticket lookup."""
    return {
        "status": "not_found",
        "match_type": "exact_ticket",
        "ticket": None,
        "error": {
            "code": code,
            "message": message,
        },
    }


def get_ticket(ticket_id: object) -> dict[str, Any]:
    """Return the stored record for one exact service-ticket ID."""
    if not isinstance(ticket_id, str):
        return _ticket_not_found(
            "malformed_ticket_id",
            "Ticket ID must be text in the format TKT-0001.",
        )

    normalized_id = ticket_id.strip().upper()
    if TICKET_ID_PATTERN.fullmatch(normalized_id) is None:
        return _ticket_not_found(
            "malformed_ticket_id",
            "Ticket ID must be text in the format TKT-0001.",
        )

    ticket = next(
        (
            stored_ticket
            for stored_ticket in load_service_tickets()
            if stored_ticket.ticket_id.upper() == normalized_id
        ),
        None,
    )
    if ticket is None:
        return _ticket_not_found(
            "ticket_not_found",
            f"No ticket found with exact ID '{normalized_id}'.",
        )

    return {
        "status": "found",
        "match_type": "exact_ticket",
        "ticket": asdict(ticket),
        "error": None,
    }


def _symptom_words(symptom: str) -> set[str]:
    """Normalize free text into words for deterministic tag comparison."""
    return set(re.findall(r"[a-z0-9]+", symptom.lower()))


def find_similar_incidents(asset_id: object, symptom: object) -> dict[str, Any]:
    """Find closed same-model incidents with stored tags present in a symptom.

    Results are historical relationships, not diagnoses of the current fault.
    """
    asset_result = get_asset_details(asset_id)
    if asset_result["status"] == "not_found":
        return {
            "status": "not_found",
            "asset_id": None,
            "asset_model": None,
            "incidents": [],
            "returned_count": 0,
            "explanation": None,
            "disclaimer": None,
            "error": asset_result["error"],
        }

    normalized_id = asset_result["asset"]["asset_id"]
    asset_model = asset_result["asset"]["model"]
    if not isinstance(symptom, str) or not symptom.strip():
        return {
            "status": "invalid_request",
            "asset_id": normalized_id,
            "asset_model": asset_model,
            "incidents": [],
            "returned_count": 0,
            "explanation": None,
            "disclaimer": None,
            "error": {
                "code": "invalid_symptom",
                "message": "Symptom must be non-empty text.",
            },
        }

    query_words = _symptom_words(symptom)
    assets_by_id = {asset.asset_id.upper(): asset for asset in load_assets()}
    incidents = []
    for ticket in load_service_tickets():
        candidate_asset = assets_by_id[ticket.asset_id.upper()]
        if candidate_asset.model.casefold() != asset_model.casefold():
            continue
        if ticket.status != "resolved" or ticket.closed_date is None:
            continue

        matched_tags = [
            tag for tag in ticket.symptom_tags if tag in query_words
        ]
        if not matched_tags:
            continue

        incidents.append(
            {
                "match_type": "related_incident",
                "ticket": asdict(ticket),
                "evidence": {
                    "asset_model": candidate_asset.model,
                    "matched_symptom_tags": matched_tags,
                    "closed_date": ticket.closed_date,
                },
            }
        )

    incidents.sort(
        key=lambda incident: (
            len(incident["evidence"]["matched_symptom_tags"]),
            incident["evidence"]["closed_date"],
            incident["ticket"]["ticket_id"],
        ),
        reverse=True,
    )
    explanation = None
    if not incidents:
        explanation = (
            "No closed same-model incidents matched the supplied symptom tags."
        )

    return {
        "status": "found",
        "asset_id": normalized_id,
        "asset_model": asset_model,
        "incidents": incidents,
        "returned_count": len(incidents),
        "explanation": explanation,
        "disclaimer": (
            "Related incidents are historical evidence only and do not prove "
            "the cause of the current symptom."
        ),
        "error": None,
    }
