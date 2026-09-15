"""Single-agent orchestration for the Asset Service Assistant."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable

from agents import Agent, RunContextWrapper, Runner, function_tool
from dotenv import load_dotenv

from asset_tools import (
    find_similar_incidents,
    get_asset_details,
    get_maintenance_history,
    get_ticket,
)
from manual_tools import search_manual


AGENT_INSTRUCTIONS = """You are the read-only Asset Service Assistant for a
maintenance service-desk coordinator. Base every asset, service, incident, and
manual claim on tool output. Never invent a record, measurement, citation, or
conclusion.

Tool routing:
- Use get_asset_details for exact asset-record questions.
- Use get_ticket only for an exact ticket question containing an explicit ID in
  the format TKT-0001. Never pass an MNT maintenance-event ID to get_ticket.
- Before get_maintenance_history, find_similar_incidents, or search_manual,
  first call get_asset_details with that exact asset ID. Continue only when it
  returns status "found".
- Use get_maintenance_history for recorded service history.
- Use find_similar_incidents only for historical same-model incident evidence;
  never present it as a diagnosis.
- Use search_manual for informational maintenance guidance. Cite the returned
  manual title, section title and ID, version, and source file. Never present a
  superseded passage as current guidance.
- For a combined question, call every relevant tool before answering, but do
  not call tools unrelated to the user's requested information.

Failure and safety behavior:
- If a tool returns not_found, invalid_request, unavailable, or an error, state
  the exact limitation clearly. Do not call a dependent tool after an invalid
  asset ID and do not fill gaps from general knowledge.
- The tools are read-only. Refuse requests to operate equipment or create,
  change, approve, close, or dispatch records.
- Do not diagnose faults, authorize repairs or continued operation, declare an
  asset safe, or bypass guards, alarms, interlocks, lockout/tagout, or maker
  procedures.
- For fire, smoke, fuel or chemical leakage, exposed electrical parts, brake or
  steering failure, uncontrolled movement, or serious-injury risk: advise the
  coordinator to stop using the asset when safe, follow the emergency process,
  and contact a qualified technician.
"""


@dataclass
class ToolExecutionContext:
    """Per-run validation state and user-visible tool limitations."""

    validated_asset_ids: set[str] = field(default_factory=set)
    tool_calls: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AssistantResult:
    """Final answer plus inspectable orchestration metadata."""

    answer: str
    tool_calls: tuple[str, ...]
    limitations: tuple[str, ...]


def _record_result(
    context: ToolExecutionContext,
    tool_name: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    context.tool_calls.append(tool_name)
    error = result.get("error")
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        message = error["message"].strip()
        if message and message not in context.limitations:
            context.limitations.append(message)
    return result


def _unavailable_result(
    context: ToolExecutionContext,
    tool_name: str,
    error: Exception,
) -> dict[str, Any]:
    message = f"{tool_name} is unavailable: {error}"
    return _record_result(
        context,
        tool_name,
        {
            "status": "unavailable",
            "error": {"code": "tool_unavailable", "message": message},
        },
    )


def _asset_details(
    context: ToolExecutionContext,
    asset_id: str,
) -> dict[str, Any]:
    try:
        result = get_asset_details(asset_id)
    except Exception as error:  # pragma: no cover - defensive boundary
        return _unavailable_result(context, "get_asset_details", error)

    _record_result(context, "get_asset_details", result)
    if result.get("status") == "found":
        context.validated_asset_ids.add(result["asset"]["asset_id"])
    return result


def _validated_asset_id(
    context: ToolExecutionContext,
    asset_id: str,
    tool_name: str,
) -> str | None:
    if not isinstance(asset_id, str):
        normalized_id = ""
    else:
        normalized_id = asset_id.strip().upper()
    if normalized_id in context.validated_asset_ids:
        return normalized_id

    result = {
        "status": "invalid_request",
        "error": {
            "code": "asset_validation_required",
            "message": (
                f"{tool_name} was not run because asset ID '{normalized_id or asset_id}' "
                "has not been validated by a successful get_asset_details call."
            ),
        },
    }
    _record_result(context, tool_name, result)
    return None


def _maintenance_history(
    context: ToolExecutionContext,
    asset_id: str,
    limit: int | None = None,
) -> dict[str, Any]:
    normalized_id = _validated_asset_id(
        context, asset_id, "get_maintenance_history"
    )
    if normalized_id is None:
        return {
            "status": "invalid_request",
            "events": [],
            "error": {
                "code": "asset_validation_required",
                "message": context.limitations[-1],
            },
        }
    try:
        result = get_maintenance_history(normalized_id, limit)
    except Exception as error:  # pragma: no cover - defensive boundary
        return _unavailable_result(context, "get_maintenance_history", error)
    return _record_result(context, "get_maintenance_history", result)


def _ticket(context: ToolExecutionContext, ticket_id: str) -> dict[str, Any]:
    try:
        result = get_ticket(ticket_id)
    except Exception as error:  # pragma: no cover - defensive boundary
        return _unavailable_result(context, "get_ticket", error)
    return _record_result(context, "get_ticket", result)


def _similar_incidents(
    context: ToolExecutionContext,
    asset_id: str,
    symptom: str,
) -> dict[str, Any]:
    normalized_id = _validated_asset_id(
        context, asset_id, "find_similar_incidents"
    )
    if normalized_id is None:
        return {
            "status": "invalid_request",
            "incidents": [],
            "error": {
                "code": "asset_validation_required",
                "message": context.limitations[-1],
            },
        }
    try:
        result = find_similar_incidents(normalized_id, symptom)
    except Exception as error:  # pragma: no cover - defensive boundary
        return _unavailable_result(context, "find_similar_incidents", error)
    return _record_result(context, "find_similar_incidents", result)


def _manual_search(
    context: ToolExecutionContext,
    asset_id: str,
    question: str,
) -> dict[str, Any]:
    normalized_id = _validated_asset_id(context, asset_id, "search_manual")
    if normalized_id is None:
        return {
            "status": "invalid_request",
            "results": [],
            "error": {
                "code": "asset_validation_required",
                "message": context.limitations[-1],
            },
        }
    try:
        result = search_manual(normalized_id, question)
    except Exception as error:  # pragma: no cover - defensive boundary
        return _unavailable_result(context, "search_manual", error)
    return _record_result(context, "search_manual", result)


def _as_json(result: dict[str, Any]) -> str:
    return json.dumps(result, sort_keys=True)


@function_tool(name_override="get_asset_details")
def asset_details_tool(
    ctx: RunContextWrapper[ToolExecutionContext],
    asset_id: str,
) -> str:
    """Retrieve one exact stored asset record and validate its asset ID.

    Args:
        ctx: Agents SDK run context containing per-run validation state.
        asset_id: Exact asset ID in the format ABC-1234.
    """
    return _as_json(_asset_details(ctx.context, asset_id))


@function_tool(name_override="get_maintenance_history")
def maintenance_history_tool(
    ctx: RunContextWrapper[ToolExecutionContext],
    asset_id: str,
    limit: int | None = None,
) -> str:
    """Retrieve recorded maintenance events after exact asset validation.

    Args:
        ctx: Agents SDK run context containing per-run validation state.
        asset_id: Exact asset ID already validated with get_asset_details.
        limit: Optional positive maximum number of newest events.
    """
    return _as_json(_maintenance_history(ctx.context, asset_id, limit))


@function_tool(name_override="get_ticket")
def ticket_tool(
    ctx: RunContextWrapper[ToolExecutionContext],
    ticket_id: str,
) -> str:
    """Retrieve one exact stored service-ticket record.

    Args:
        ctx: Agents SDK run context containing per-run validation state.
        ticket_id: Exact ticket ID in the format TKT-0001.
    """
    return _as_json(_ticket(ctx.context, ticket_id))


@function_tool(name_override="find_similar_incidents")
def similar_incidents_tool(
    ctx: RunContextWrapper[ToolExecutionContext],
    asset_id: str,
    symptom: str,
) -> str:
    """Find closed same-model incidents as evidence, not diagnosis.

    Args:
        ctx: Agents SDK run context containing per-run validation state.
        asset_id: Exact asset ID already validated with get_asset_details.
        symptom: Current symptom text used for deterministic tag matching.
    """
    return _as_json(_similar_incidents(ctx.context, asset_id, symptom))


@function_tool(name_override="search_manual")
def manual_search_tool(
    ctx: RunContextWrapper[ToolExecutionContext],
    asset_id: str,
    question: str,
) -> str:
    """Search applicable manuals for grounded, citable passages.

    Args:
        ctx: Agents SDK run context containing per-run validation state.
        asset_id: Exact asset ID already validated with get_asset_details.
        question: Informational maintenance question to retrieve evidence for.
    """
    return _as_json(_manual_search(ctx.context, asset_id, question))


TOOLS = [
    asset_details_tool,
    maintenance_history_tool,
    ticket_tool,
    similar_incidents_tool,
    manual_search_tool,
]


def create_agent(model: str | None = None) -> Agent[ToolExecutionContext]:
    """Create the single read-only assistant with all deterministic tools."""
    return Agent(
        name="Asset Service Assistant",
        instructions=AGENT_INSTRUCTIONS,
        tools=TOOLS,
        model=model,
    )


RunnerFunction = Callable[..., Any]


def run_assistant(
    question: str,
    *,
    model: str | None = None,
    runner: RunnerFunction = Runner.run_sync,
) -> AssistantResult:
    """Run one user question and return the answer plus tool-call evidence."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question must be non-empty text.")

    context = ToolExecutionContext()
    try:
        result = runner(
            create_agent(model),
            question.strip(),
            context=context,
            max_turns=10,
        )
        answer = str(result.final_output).strip()
    except Exception as error:
        message = (
            "The assistant could not complete the request because the agent "
            f"run failed ({type(error).__name__})."
        )
        return AssistantResult(message, tuple(context.tool_calls), (message,))

    missing_limitations = [
        message
        for message in context.limitations
        if message.casefold() not in answer.casefold()
    ]
    if missing_limitations:
        answer = f"{answer}\n\nLimitations:\n" + "\n".join(
            f"- {message}" for message in missing_limitations
        )
    return AssistantResult(
        answer,
        tuple(context.tool_calls),
        tuple(context.limitations),
    )


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Ask the read-only Asset Service Assistant a question"
    )
    parser.add_argument("question", nargs="+", help="Question for the assistant")
    parser.add_argument(
        "--model",
        default=os.getenv("ASA_AGENT_MODEL"),
        help="Optional OpenAI model override (or set ASA_AGENT_MODEL)",
    )
    args = parser.parse_args()

    result = run_assistant(" ".join(args.question), model=args.model)
    print(result.answer)


if __name__ == "__main__":
    main()
