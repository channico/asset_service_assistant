import json
import tempfile
import unittest
from pathlib import Path

from evaluate_manual_search import DEFAULT_CASES_PATH, load_cases
from manual_tools import DEFAULT_MIN_SIMILARITY


class ManualSearchEvaluationTests(unittest.TestCase):
    def test_fixture_has_required_calibration_and_held_out_cases(self) -> None:
        fixture = load_cases(DEFAULT_CASES_PATH)
        cases = fixture["cases"]
        identifiers = [case["id"] for case in cases]
        calibration_categories = {
            case["category"]
            for case in cases
            if case["phase"] == "calibration"
        }

        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertEqual(fixture["frozen_threshold"], DEFAULT_MIN_SIMILARITY)
        self.assertTrue(any(case["phase"] == "held_out" for case in cases))
        self.assertLessEqual(
            {"relevant", "paraphrased", "borderline", "wrong-model", "unsupported"},
            calibration_categories,
        )

    def test_fixture_cannot_silently_retune_the_application_threshold(self) -> None:
        fixture = json.loads(DEFAULT_CASES_PATH.read_text(encoding="utf-8"))
        fixture["frozen_threshold"] = DEFAULT_MIN_SIMILARITY + 0.01

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            path.write_text(json.dumps(fixture), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "frozen application threshold"):
                load_cases(path)


if __name__ == "__main__":
    unittest.main()
