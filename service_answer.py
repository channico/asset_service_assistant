"""Structured final answers and deterministic rendering for the assistant."""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class AnswerModel(BaseModel):
    """Strict base model used by every final-answer component."""

    model_config = ConfigDict(extra="forbid")


class AssetIdentity(AnswerModel):
    """Exact identity fields copied from one validated asset record."""

    asset_id: NonEmptyText
    name: NonEmptyText
    asset_type: NonEmptyText
    manufacturer: NonEmptyText
    model: NonEmptyText
    year: int
    location: NonEmptyText
    recorded_status: NonEmptyText


class ConfirmedFact(AnswerModel):
    """A stored fact with an inspectable record reference."""

    source_type: Literal[
        "asset_record",
        "maintenance_event",
        "service_ticket",
        "related_incident",
    ]
    source_id: NonEmptyText
    statement: NonEmptyText


class ManualCitation(AnswerModel):
    """The complete source identity for one current manual passage."""

    manual_id: NonEmptyText
    manual_title: NonEmptyText
    section_id: NonEmptyText
    section_title: NonEmptyText
    version: NonEmptyText
    version_status: Literal["current"]
    source_file: NonEmptyText


class ManualGuidance(AnswerModel):
    """A manual-derived recommendation with at least one citation."""

    recommendation: NonEmptyText
    citations: list[ManualCitation] = Field(min_length=1)


class EvidenceGap(AnswerModel):
    """Information that was required but not established by retrieved evidence."""

    missing: NonEmptyText
    impact: NonEmptyText


class Uncertainty(AnswerModel):
    """A conclusion the available evidence cannot support."""

    unresolved: NonEmptyText
    reason: NonEmptyText


class Escalation(AnswerModel):
    """Required qualified-human review and the reason for it."""

    triggering_rule: NonEmptyText
    available_evidence: list[NonEmptyText]
    unknowns: list[NonEmptyText] = Field(min_length=1)
    immediate_action: NonEmptyText
    qualified_review: NonEmptyText


class ServiceAnswer(AnswerModel):
    """The complete evidence-based answer returned by the agent."""

    summary: NonEmptyText
    asset_identity: AssetIdentity | None
    confirmed_history: list[ConfirmedFact]
    manual_guidance: list[ManualGuidance]
    missing_information: list[EvidenceGap]
    uncertainties: list[Uncertainty]
    escalation: Escalation | None


def _citation_key(citation: ManualCitation) -> tuple[str, ...]:
    return (
        citation.manual_id,
        citation.manual_title,
        citation.section_id,
        citation.section_title,
        citation.version,
        citation.version_status,
        citation.source_file,
    )


def _result_citation_key(result: dict[str, Any]) -> tuple[str, ...] | None:
    try:
        document = result["document"]
        section = result["section"]
        version = result["version"]
        return (
            document["manual_id"],
            document["title"],
            section["section_id"],
            section["title"],
            version["number"],
            version["status"],
            document["source_file"],
        )
    except (KeyError, TypeError):
        return None


def validate_manual_citations(
    answer: ServiceAnswer,
    tool_results: list[tuple[str, dict[str, Any]]],
) -> None:
    """Reject manual citations that were not returned during this agent run."""
    retrieved_citations: set[tuple[str, ...]] = set()
    for tool_name, tool_result in tool_results:
        if tool_name != "search_manual" or tool_result.get("status") != "found":
            continue
        for result in tool_result.get("results", []):
            citation_key = _result_citation_key(result)
            if citation_key is not None and citation_key[5] == "current":
                retrieved_citations.add(citation_key)

    for guidance in answer.manual_guidance:
        for citation in guidance.citations:
            if _citation_key(citation) not in retrieved_citations:
                raise ValueError(
                    "Final answer contains a manual citation that was not returned "
                    "as current guidance by search_manual."
                )


def add_context_limitations(
    answer: ServiceAnswer,
    limitations: list[str],
) -> ServiceAnswer:
    """Ensure tool limitations appear in the structured evidence-gap section."""
    existing = {gap.missing.casefold() for gap in answer.missing_information}
    additions = [
        EvidenceGap(
            missing=message,
            impact="This part of the request could not be confirmed from project data.",
        )
        for message in limitations
        if message.casefold() not in existing
    ]
    if not additions:
        return answer
    return answer.model_copy(
        update={"missing_information": [*answer.missing_information, *additions]}
    )


_SAFETY_PATTERNS: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (
        re.compile(
            r"\b(fire|smok(?:e|ing)|fuel (?:leak|leakage|is leaking)|"
            r"chemical (?:leak|leakage|is leaking)|(?:leaking|leakage of) "
            r"(?:fuel|chemical)|exposed electrical|brakes? "
            r"(?:failed|failing|failure)|steering (?:failed|failing|failure)|"
            r"uncontrolled movement|moves? uncontrollably|"
            r"serious[- ]injury risk)\b",
            re.IGNORECASE,
        ),
        "Safety-critical symptom",
        (
            "Stop using the asset when safe to do so and follow the applicable "
            "emergency process."
        ),
    ),
    (
        re.compile(
            r"\b(?:bypass|disable|override)\b.{0,50}\b(?:guard|alarm|interlock|"
            r"lockout(?:/tagout)?|tagout|safety (?:control|procedure))s?\b",
            re.IGNORECASE,
        ),
        "Safety-control bypass request",
        (
            "Do not bypass or disable guards, alarms, interlocks, lockout/tagout, "
            "or manufacturer safety procedures."
        ),
    ),
    (
        re.compile(
            r"\b(safe to (?:use|operate|drive)|return(?:ed)? to service|"
            r"authorize (?:the )?repair|definitive diagnosis|diagnose (?:the|this)|"
            r"continue to (?:use|operate|drive)|keep (?:using|operating|driving))\b",
            re.IGNORECASE,
        ),
        "Repair, diagnosis, or return-to-service decision",
        (
            "Do not use this assistant response as a diagnosis, repair authorization, "
            "or return-to-service approval."
        ),
    ),
)


def ensure_required_escalation(
    question: str,
    answer: ServiceAnswer,
) -> ServiceAnswer:
    """Add the mandatory escalation for deterministic safety-rule matches."""
    for pattern, rule, immediate_action in _SAFETY_PATTERNS:
        if pattern.search(question) is None:
            continue
        evidence = [fact.statement for fact in answer.confirmed_history]
        if answer.asset_identity is not None:
            evidence.insert(
                0,
                (
                    f"Validated asset {answer.asset_identity.asset_id}: "
                    f"{answer.asset_identity.manufacturer} "
                    f"{answer.asset_identity.model}."
                ),
            )
        escalation = Escalation(
            triggering_rule=rule,
            available_evidence=evidence,
            unknowns=[
                "The retrieved evidence does not establish the current fault cause "
                "or confirm that the asset is safe to operate."
            ],
            immediate_action=immediate_action,
            qualified_review=(
                "Contact a qualified technician to inspect the asset and make any "
                "diagnosis, repair, or return-to-service decision."
            ),
        )
        return answer.model_copy(update={"escalation": escalation})
    return answer


def failure_answer(message: str) -> ServiceAnswer:
    """Build a structured response when the agent run cannot complete."""
    return ServiceAnswer(
        summary="The assistant could not complete the request.",
        asset_identity=None,
        confirmed_history=[],
        manual_guidance=[],
        missing_information=[
            EvidenceGap(
                missing=message,
                impact="No evidence-based service answer could be produced.",
            )
        ],
        uncertainties=[
            Uncertainty(
                unresolved="The requested asset or service information remains unknown.",
                reason="The agent run did not complete successfully.",
            )
        ],
        escalation=None,
    )


def _single_line(text: str) -> str:
    return " ".join(text.split())


def render_service_answer(answer: ServiceAnswer) -> str:
    """Render a validated answer into stable, human-readable Markdown."""
    lines = [_single_line(answer.summary), "", "## Asset identity"]

    if answer.asset_identity is None:
        lines.append("- No validated asset identity was retrieved.")
    else:
        asset = answer.asset_identity
        lines.extend(
            [
                f"- **Asset ID:** {_single_line(asset.asset_id)}",
                f"- **Name:** {_single_line(asset.name)}",
                f"- **Type:** {_single_line(asset.asset_type)}",
                (
                    f"- **Make and model:** {_single_line(asset.manufacturer)} "
                    f"{_single_line(asset.model)} ({asset.year})"
                ),
                f"- **Location:** {_single_line(asset.location)}",
                f"- **Recorded status:** {_single_line(asset.recorded_status)}",
            ]
        )

    lines.extend(["", "## Confirmed history"])
    if not answer.confirmed_history:
        lines.append("- No confirmed maintenance or ticket history was retrieved.")
    else:
        for fact in answer.confirmed_history:
            lines.append(
                f"- {_single_line(fact.statement)} "
                f"`[{fact.source_type}: {_single_line(fact.source_id)}]`"
            )

    lines.extend(["", "## Manual guidance"])
    if not answer.manual_guidance:
        lines.append("- No current, citable manual guidance was retrieved.")
    else:
        for guidance in answer.manual_guidance:
            lines.append(f"- {_single_line(guidance.recommendation)}")
            for citation in guidance.citations:
                lines.append(
                    "  - Source: "
                    f"{_single_line(citation.manual_title)} "
                    f"({_single_line(citation.manual_id)}), "
                    f"{_single_line(citation.section_title)} "
                    f"({_single_line(citation.section_id)}), "
                    f"version {_single_line(citation.version)} "
                    f"[{citation.version_status.upper()}], "
                    f"`{_single_line(citation.source_file)}`"
                )

    lines.extend(["", "## Missing information and uncertainty"])
    if not answer.missing_information and not answer.uncertainties:
        lines.append("- No evidence gaps or unresolved uncertainty were identified.")
    else:
        for gap in answer.missing_information:
            lines.append(
                f"- **Missing:** {_single_line(gap.missing)} "
                f"**Impact:** {_single_line(gap.impact)}"
            )
        for uncertainty in answer.uncertainties:
            lines.append(
                f"- **Uncertain:** {_single_line(uncertainty.unresolved)} "
                f"**Reason:** {_single_line(uncertainty.reason)}"
            )

    if answer.escalation is not None:
        escalation = answer.escalation
        lines.extend(
            [
                "",
                "## Escalation",
                f"- **Trigger:** {_single_line(escalation.triggering_rule)}",
            ]
        )
        for evidence in escalation.available_evidence:
            lines.append(f"- **Available evidence:** {_single_line(evidence)}")
        for unknown in escalation.unknowns:
            lines.append(f"- **Unknown:** {_single_line(unknown)}")
        lines.extend(
            [
                f"- **Immediate action:** {_single_line(escalation.immediate_action)}",
                f"- **Qualified review:** {_single_line(escalation.qualified_review)}",
            ]
        )

    return "\n".join(lines)
