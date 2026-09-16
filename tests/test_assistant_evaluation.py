import json
import tempfile
import unittest
from pathlib import Path

from assistant_agent import AssistantResult
from evaluate_assistant import (
    DEFAULT_CASES_PATH,
    evaluate_cases,
    evaluate_result,
    load_cases,
)


STRUCTURED_EMPTY_ANSWER = """Grounded response

## Asset identity
- No validated asset identity was retrieved.

## Confirmed history
- No confirmed maintenance or ticket history was retrieved.

## Manual guidance
- No current, citable manual guidance was retrieved.

## Missing information and uncertainty
- No evidence gaps or unresolved uncertainty were identified."""


class AssistantEvaluationFixtureTests(unittest.TestCase):
    def test_fixture_has_required_coverage_and_recorded_expectations(self) -> None:
        cases = load_cases(DEFAULT_CASES_PATH)["cases"]
        identifiers = [case["id"] for case in cases]
        categories = {case["category"] for case in cases}

        self.assertGreaterEqual(len(cases), 10)
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertLessEqual(
            {"valid", "missing", "conflicting", "unsupported"}, categories
        )
        for case in cases:
            self.assertIn("required", case["expected_tools"])
            self.assertIn("forbidden", case["expected_tools"])
            self.assertIn("ordered_pairs", case["expected_tools"])
            self.assertTrue(case["expected_answer"]["characteristics"])

    def test_fixture_rejects_fewer_than_ten_cases(self) -> None:
        fixture = json.loads(DEFAULT_CASES_PATH.read_text(encoding="utf-8"))
        fixture["cases"] = fixture["cases"][:9]

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            path.write_text(json.dumps(fixture), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "at least 10"):
                load_cases(path)


class AssistantEvaluationLogicTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case = {
            "id": "test-case",
            "category": "valid",
            "question": "Question",
            "expected_tools": {
                "required": ["get_asset_details", "get_maintenance_history"],
                "forbidden": ["search_manual"],
                "ordered_pairs": [
                    ["get_asset_details", "get_maintenance_history"]
                ],
            },
            "expected_answer": {
                "characteristics": ["test expectation"],
                "asset_identity": "absent",
                "confirmed_history": "absent",
                "manual_guidance": "absent",
                "evidence_gap": "absent",
                "escalation": "absent",
                "required_text": ["Grounded response"],
            },
        }

    def test_passes_matching_routing_and_answer(self) -> None:
        result = AssistantResult(
            STRUCTURED_EMPTY_ANSWER,
            ("get_asset_details", "get_maintenance_history"),
            (),
        )

        evaluation = evaluate_result(self.case, result)

        self.assertTrue(evaluation.passed)
        self.assertEqual(evaluation.failures, ())

    def test_detects_missing_forbidden_and_misordered_tools(self) -> None:
        result = AssistantResult(
            STRUCTURED_EMPTY_ANSWER,
            ("get_maintenance_history", "search_manual"),
            (),
        )

        evaluation = evaluate_result(self.case, result)

        self.assertFalse(evaluation.passed)
        self.assertTrue(
            any("required tool" in failure for failure in evaluation.failures)
        )
        self.assertTrue(
            any("forbidden tool" in failure for failure in evaluation.failures)
        )
        self.assertTrue(any("before" in failure for failure in evaluation.failures))

    def test_evaluate_cases_supports_an_offline_injected_runner(self) -> None:
        calls = []

        def fake_runner(question: str, *, model: str) -> AssistantResult:
            calls.append((question, model))
            return AssistantResult(
                STRUCTURED_EMPTY_ANSWER,
                ("get_asset_details", "get_maintenance_history"),
                (),
            )

        results = evaluate_cases([self.case], model="test-model", runner=fake_runner)

        self.assertTrue(results[0].passed)
        self.assertEqual(calls, [("Question", "test-model")])


if __name__ == "__main__":
    unittest.main()
