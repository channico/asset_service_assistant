"""Load synthetic maintenance events and service tickets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from asset_repository import Asset, load_assets


PROJECT_ROOT = Path(__file__).parent
DEFAULT_MAINTENANCE_FILE = (
    PROJECT_ROOT / "data" / "maintenance_history" / "maintenance_events.json"
)
DEFAULT_TICKET_FILE = (
    PROJECT_ROOT / "data" / "service_tickets" / "service_tickets.json"
)

VALID_MAINTENANCE_STATUSES = {"completed", "follow_up_required"}
VALID_TICKET_STATUSES = {"open", "in_progress", "resolved", "escalated"}
VALID_PRIORITIES = {"low", "medium", "high", "critical"}


def _require_text(record: dict[str, Any], fields: tuple[str, ...], kind: str) -> None:
    """Reject absent, empty, or non-text required fields."""
    for field in fields:
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{kind} field '{field}' must be a non-empty string")


def _require_iso_date(value: str, field: str, kind: str) -> None:
    """Require an ISO date such as 2026-09-16."""
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(
            f"{kind} field '{field}' must use YYYY-MM-DD format"
        ) from error


def _load_json_array(path: Path, kind: str) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as file:
        records = json.load(file)
    if not isinstance(records, list) or not all(
        isinstance(item, dict) for item in records
    ):
        raise ValueError(f"The {kind} data file must contain a JSON array of objects")
    return records


def _reject_duplicate_ids(identifiers: list[str], field: str) -> None:
    normalized = [identifier.upper() for identifier in identifiers]
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"Every {field} must be unique")


@dataclass(frozen=True)
class MaintenanceEvent:
    maintenance_id: str
    asset_id: str
    service_date: str
    maintenance_type: str
    symptom: str
    action_taken: str
    repair_outcome: str
    status: str

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "MaintenanceEvent":
        kind = "Maintenance event"
        fields = (
            "maintenance_id",
            "asset_id",
            "service_date",
            "maintenance_type",
            "symptom",
            "action_taken",
            "repair_outcome",
            "status",
        )
        _require_text(record, fields, kind)
        _require_iso_date(record["service_date"], "service_date", kind)
        if record["status"] not in VALID_MAINTENANCE_STATUSES:
            raise ValueError(f"Unknown maintenance status '{record['status']}'")
        return cls(**{field: record[field] for field in fields})


@dataclass(frozen=True)
class ServiceTicket:
    ticket_id: str
    asset_id: str
    opened_date: str
    closed_date: str | None
    status: str
    priority: str
    symptom: str
    symptom_tags: list[str]
    repair_outcome: str | None

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "ServiceTicket":
        kind = "Service ticket"
        fields = (
            "ticket_id",
            "asset_id",
            "opened_date",
            "status",
            "priority",
            "symptom",
        )
        _require_text(record, fields, kind)
        _require_iso_date(record["opened_date"], "opened_date", kind)

        closed_date = record.get("closed_date")
        if closed_date is not None:
            if not isinstance(closed_date, str):
                raise ValueError(
                    "Service ticket field 'closed_date' must be a string or null"
                )
            _require_iso_date(closed_date, "closed_date", kind)

        repair_outcome = record.get("repair_outcome")
        if repair_outcome is not None and (
            not isinstance(repair_outcome, str) or not repair_outcome.strip()
        ):
            raise ValueError(
                "Service ticket field 'repair_outcome' must be a non-empty string or null"
            )

        symptom_tags = record.get("symptom_tags")
        if not isinstance(symptom_tags, list) or not symptom_tags:
            raise ValueError(
                "Service ticket field 'symptom_tags' must be a non-empty list"
            )
        if any(
            not isinstance(tag, str) or not tag.strip() for tag in symptom_tags
        ):
            raise ValueError(
                "Every service ticket symptom tag must be a non-empty string"
            )
        normalized_tags = [tag.strip().lower() for tag in symptom_tags]
        if len(normalized_tags) != len(set(normalized_tags)):
            raise ValueError("Service ticket symptom tags must be unique")

        if record["status"] not in VALID_TICKET_STATUSES:
            raise ValueError(f"Unknown ticket status '{record['status']}'")
        if record["priority"] not in VALID_PRIORITIES:
            raise ValueError(f"Unknown ticket priority '{record['priority']}'")

        return cls(
            ticket_id=record["ticket_id"],
            asset_id=record["asset_id"],
            opened_date=record["opened_date"],
            closed_date=closed_date,
            status=record["status"],
            priority=record["priority"],
            symptom=record["symptom"],
            symptom_tags=normalized_tags,
            repair_outcome=repair_outcome,
        )


def load_maintenance_events(
    path: Path = DEFAULT_MAINTENANCE_FILE,
) -> list[MaintenanceEvent]:
    records = _load_json_array(path, "maintenance event")
    events = [MaintenanceEvent.from_dict(record) for record in records]
    _reject_duplicate_ids(
        [event.maintenance_id for event in events], "maintenance_id"
    )
    return events


def load_service_tickets(path: Path = DEFAULT_TICKET_FILE) -> list[ServiceTicket]:
    records = _load_json_array(path, "service ticket")
    tickets = [ServiceTicket.from_dict(record) for record in records]
    _reject_duplicate_ids([ticket.ticket_id for ticket in tickets], "ticket_id")
    return tickets


def validate_asset_references(
    assets: list[Asset],
    events: list[MaintenanceEvent],
    tickets: list[ServiceTicket],
) -> None:
    """Ensure every maintenance event and ticket refers to a known asset."""
    asset_ids = {asset.asset_id.upper() for asset in assets}
    missing_references = [
        f"maintenance event {event.maintenance_id} -> {event.asset_id}"
        for event in events
        if event.asset_id.upper() not in asset_ids
    ]
    missing_references.extend(
        f"service ticket {ticket.ticket_id} -> {ticket.asset_id}"
        for ticket in tickets
        if ticket.asset_id.upper() not in asset_ids
    )
    if missing_references:
        details = ", ".join(missing_references)
        raise ValueError(f"Records reference missing asset IDs: {details}")


def load_and_validate_data() -> tuple[
    list[Asset], list[MaintenanceEvent], list[ServiceTicket]
]:
    """Load the complete synthetic dataset and validate its relationships."""
    assets = load_assets()
    events = load_maintenance_events()
    tickets = load_service_tickets()
    validate_asset_references(assets, events, tickets)
    return assets, events, tickets
