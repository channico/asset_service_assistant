"""Stakeholder-facing Streamlit UI for the Asset Service Assistant."""

from __future__ import annotations

import os
from typing import Final

import streamlit as st
from dotenv import load_dotenv

from assistant_agent import AssistantResult, run_assistant
from service_answer import ServiceAnswer


DEMO_QUESTIONS: Final[tuple[tuple[str, str, str], ...]] = (
    (
        "Asset and history",
        "Exact synthetic records",
        "Show asset VEH-1001 and its recorded maintenance history.",
    ),
    (
        "Manual guidance",
        "Current guidance with citations",
        (
            "For VEH-1001, what should I record if the sliding door has "
            "resistance, abnormal noise, or incomplete latching?"
        ),
    ),
    (
        "Safety boundary",
        "Unsupported diagnosis and approval",
        (
            "For VEH-1001, diagnose the fault, prescribe the exact repair, "
            "and confirm it is safe to drive."
        ),
    ),
)


def _render_asset_identity(answer: ServiceAnswer) -> None:
    st.subheader("Asset identity")
    asset = answer.asset_identity
    if asset is None:
        st.caption("No validated asset identity was retrieved.")
        return

    first, second, third = st.columns(3)
    first.metric("Asset ID", asset.asset_id)
    second.metric("Recorded status", asset.recorded_status)
    third.metric("Year", str(asset.year))
    st.markdown(
        f"**{asset.name}** · {asset.asset_type} · "
        f"{asset.manufacturer} {asset.model} · {asset.location}"
    )


def _render_confirmed_history(answer: ServiceAnswer) -> None:
    st.subheader("Confirmed history")
    if not answer.confirmed_history:
        st.caption("No confirmed maintenance or ticket history was retrieved.")
        return

    for fact in answer.confirmed_history:
        st.markdown(
            f"- {fact.statement}  \n"
            f"  `{fact.source_type}: {fact.source_id}`"
        )


def _render_manual_guidance(answer: ServiceAnswer) -> None:
    st.subheader("Manual guidance and citations")
    if not answer.manual_guidance:
        st.caption("No current, citable manual guidance was retrieved.")
        return

    for item in answer.manual_guidance:
        st.markdown(f"- {item.recommendation}")
        for citation in item.citations:
            st.caption(
                f"Source: {citation.manual_title} ({citation.manual_id}) · "
                f"{citation.section_title} ({citation.section_id}) · "
                f"version {citation.version} [{citation.version_status.upper()}] · "
                f"{citation.source_file}"
            )


def _render_evidence_gaps(answer: ServiceAnswer) -> None:
    st.subheader("Missing information")
    if not answer.missing_information:
        st.caption("No missing evidence was identified.")
    else:
        for gap in answer.missing_information:
            st.warning(f"{gap.missing}\n\nImpact: {gap.impact}")

    st.subheader("Uncertainty")
    if not answer.uncertainties:
        st.caption("No unresolved uncertainty was identified.")
    else:
        for uncertainty in answer.uncertainties:
            st.warning(
                f"{uncertainty.unresolved}\n\nReason: {uncertainty.reason}"
            )


def _render_escalation(answer: ServiceAnswer) -> None:
    if answer.escalation is None:
        return

    escalation = answer.escalation
    st.error(
        f"Escalation required — {escalation.triggering_rule}\n\n"
        f"Immediate action: {escalation.immediate_action}\n\n"
        f"Qualified review: {escalation.qualified_review}"
    )
    with st.expander("Escalation evidence and unknowns", expanded=True):
        st.markdown("**Available evidence**")
        if escalation.available_evidence:
            for item in escalation.available_evidence:
                st.markdown(f"- {item}")
        else:
            st.caption("No supporting project evidence was retrieved.")
        st.markdown("**Unknowns**")
        for item in escalation.unknowns:
            st.markdown(f"- {item}")


def _render_tools(result: AssistantResult) -> None:
    label = f"Tools used ({len(result.tool_calls)})"
    with st.expander(label, expanded=False):
        if result.tool_calls:
            for index, tool_name in enumerate(result.tool_calls, start=1):
                st.code(f"{index}. {tool_name}", language=None)
        else:
            st.caption("No project tools were used for this response.")

        if result.limitations:
            st.markdown("**Run limitations**")
            for limitation in result.limitations:
                st.markdown(f"- {limitation}")


def _render_result(result: AssistantResult) -> None:
    answer = result.service_answer
    if answer is None:
        st.warning("A structured response was unavailable. Showing the safe fallback.")
        st.markdown(result.answer)
        _render_tools(result)
        return

    if answer.escalation is not None:
        _render_escalation(answer)
    elif answer.missing_information or answer.uncertainties or result.limitations:
        st.warning("This response has evidence gaps or unresolved limitations.")

    st.markdown(answer.summary)
    st.divider()
    _render_asset_identity(answer)
    st.divider()
    _render_confirmed_history(answer)
    st.divider()
    _render_manual_guidance(answer)
    st.divider()
    _render_evidence_gaps(answer)
    _render_tools(result)


def _run_question(question: str) -> AssistantResult:
    with st.spinner("Checking synthetic records and read-only guidance…"):
        return run_assistant(question, model=os.getenv("ASA_AGENT_MODEL"))


def main() -> None:
    load_dotenv()
    st.set_page_config(
        page_title="Asset Service Assistant",
        page_icon="🛠️",
        layout="wide",
    )

    st.title("Asset Service Assistant")
    st.caption("A learning POC for maintenance service-desk demonstrations")
    notice_one, notice_two = st.columns(2)
    notice_one.info(
        "Synthetic data only — no real asset, customer, employee, or telemetry "
        "records are used."
    )
    notice_two.info(
        "Read-only assistant — it cannot operate equipment or create, change, "
        "approve, close, or dispatch work."
    )

    if "messages" not in st.session_state:
        st.session_state.messages = []

    st.subheader("Ask a question")
    with st.form("question-form", clear_on_submit=True):
        typed_question = st.text_input(
            "Your question",
            placeholder=(
                "Ask about an exact asset, service history, ticket, or manual guidance"
            ),
        )
        st.caption(f'Example question: "{DEMO_QUESTIONS[0][2]}"')
        typed_submitted = st.form_submit_button(
            "Ask the assistant",
            type="primary",
            use_container_width=True,
        )
    st.caption("Press Enter or select **Ask the assistant** to submit.")

    st.subheader("Or use a demonstration shortcut")
    demo_columns = st.columns(len(DEMO_QUESTIONS))
    selected_question: str | None = None
    for column, (title, description, question) in zip(
        demo_columns, DEMO_QUESTIONS, strict=True
    ):
        with column:
            st.markdown(f"**{title}**")
            st.caption(description)
            st.markdown(f"**Query:** {question}")
            if st.button("Run demo", key=f"demo-{title}", use_container_width=True):
                selected_question = question

    question: str | None = None
    if typed_submitted:
        question = typed_question.strip()
        if not question:
            st.warning("Enter a question before submitting.")
            question = None
    elif selected_question is not None:
        question = selected_question

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message["role"] == "user":
                st.markdown(message["content"])
            else:
                _render_result(message["result"])

    if question is not None:
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            result = _run_question(question)
            _render_result(result)
        st.session_state.messages.append({"role": "assistant", "result": result})


if __name__ == "__main__":
    main()
