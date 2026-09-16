import unittest
from types import SimpleNamespace
from unittest.mock import patch

from assistant_agent import (
    AGENT_INSTRUCTIONS,
    TOOLS,
    ToolExecutionContext,
    _asset_details,
    _maintenance_history,
    _manual_search,
    create_agent,
    run_assistant,
)
from service_answer import ServiceAnswer


def empty_service_answer(summary: str = "Grounded answer") -> ServiceAnswer:
    return ServiceAnswer(
        summary=summary,
        asset_identity=None,
        confirmed_history=[],
        manual_guidance=[],
        missing_information=[],
        uncertainties=[],
        escalation=None,
    )


class ToolAdapterTests(unittest.TestCase):
    def test_registers_all_five_read_only_tools(self) -> None:
        self.assertEqual(
            {tool.name for tool in TOOLS},
            {
                "get_asset_details",
                "get_maintenance_history",
                "get_ticket",
                "find_similar_incidents",
                "search_manual",
            },
        )

    @patch("assistant_agent.get_maintenance_history")
    def test_dependent_tool_stops_before_unvalidated_asset(self, history) -> None:
        context = ToolExecutionContext()

        result = _maintenance_history(context, "VEH-9999")

        history.assert_not_called()
        self.assertEqual(result["status"], "invalid_request")
        self.assertEqual(result["error"]["code"], "asset_validation_required")
        self.assertIn("not been validated", result["error"]["message"])

    @patch("assistant_agent.get_maintenance_history")
    def test_successful_exact_lookup_enables_dependent_tool(self, history) -> None:
        history.return_value = {
            "status": "found",
            "asset_id": "VEH-1001",
            "events": [],
            "error": None,
        }
        context = ToolExecutionContext()

        asset_result = _asset_details(context, "veh-1001")
        history_result = _maintenance_history(context, "VEH-1001")

        self.assertEqual(asset_result["status"], "found")
        history.assert_called_once_with("VEH-1001", None)
        self.assertEqual(history_result["status"], "found")
        self.assertEqual(
            context.tool_calls,
            ["get_asset_details", "get_maintenance_history"],
        )

    @patch("assistant_agent.search_manual")
    def test_manual_questions_use_grounded_retrieval_adapter(self, search) -> None:
        search.return_value = {
            "status": "found",
            "results": [{"passage": "Grounded evidence"}],
            "error": None,
        }
        context = ToolExecutionContext(validated_asset_ids={"VEH-1001"})

        result = _manual_search(
            context,
            "VEH-1001",
            "How should I inspect the sliding door?",
        )

        search.assert_called_once_with(
            "VEH-1001", "How should I inspect the sliding door?"
        )
        self.assertEqual(result["results"][0]["passage"], "Grounded evidence")

    @patch("assistant_agent.get_asset_details", side_effect=OSError("data offline"))
    def test_tool_exception_becomes_clear_structured_limitation(self, _lookup) -> None:
        context = ToolExecutionContext()

        result = _asset_details(context, "VEH-1001")

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["error"]["code"], "tool_unavailable")
        self.assertIn("data offline", result["error"]["message"])
        self.assertEqual(context.limitations, [result["error"]["message"]])


class AgentOrchestrationTests(unittest.TestCase):
    def test_agent_instructions_require_multi_tool_and_failure_behavior(self) -> None:
        agent = create_agent("test-model")

        self.assertEqual(agent.model, "test-model")
        self.assertIn("For a combined question", AGENT_INSTRUCTIONS)
        self.assertIn("Do not call a dependent tool", AGENT_INSTRUCTIONS)
        self.assertIn("Cite the returned", AGENT_INSTRUCTIONS)
        self.assertIn("Never pass an MNT", AGENT_INSTRUCTIONS)
        self.assertIs(agent.output_type, ServiceAnswer)

    def test_asset_dependent_tools_cannot_run_in_parallel(self) -> None:
        agent = create_agent("test-model")

        self.assertFalse(agent.model_settings.parallel_tool_calls)
        self.assertIn("in a later tool round", AGENT_INSTRUCTIONS)

    def test_run_passes_question_context_and_agent_to_runner(self) -> None:
        captured = {}

        def fake_runner(agent, question, **kwargs):
            captured.update(agent=agent, question=question, kwargs=kwargs)
            return SimpleNamespace(final_output=empty_service_answer())

        result = run_assistant(
            "  Show asset VEH-1001 and its history  ",
            model="test-model",
            runner=fake_runner,
        )

        self.assertTrue(result.answer.startswith("Grounded answer"))
        self.assertIn("## Asset identity", result.answer)
        self.assertIn("## Confirmed history", result.answer)
        self.assertIn("## Manual guidance", result.answer)
        self.assertIn("## Missing information and uncertainty", result.answer)
        self.assertIsInstance(result.service_answer, ServiceAnswer)
        self.assertEqual(captured["question"], "Show asset VEH-1001 and its history")
        self.assertIsInstance(captured["kwargs"]["context"], ToolExecutionContext)
        self.assertEqual(captured["kwargs"]["max_turns"], 10)

    def test_runner_failure_returns_user_visible_limitation(self) -> None:
        def failing_runner(*args, **kwargs):
            raise RuntimeError("provider unavailable")

        result = run_assistant("Show VEH-1001", runner=failing_runner)

        self.assertIn("could not complete", result.answer)
        self.assertIn("RuntimeError", result.answer)
        self.assertEqual(len(result.limitations), 1)
        self.assertIn("RuntimeError", result.limitations[0])
        self.assertIsInstance(result.service_answer, ServiceAnswer)

    def test_wrong_final_output_type_becomes_structured_limitation(self) -> None:
        def wrong_output_runner(*args, **kwargs):
            return SimpleNamespace(final_output="free-form answer")

        result = run_assistant("Show VEH-1001", runner=wrong_output_runner)

        self.assertIn("TypeError", result.answer)
        self.assertIn("## Missing information and uncertainty", result.answer)

    def test_blank_question_is_rejected_before_runner(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-empty"):
            run_assistant("   ")


if __name__ == "__main__":
    unittest.main()
