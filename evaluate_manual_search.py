"""Run the frozen manual-search retrieval evaluation without generating answers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from manual_tools import DEFAULT_MIN_SIMILARITY, search_manual


DEFAULT_CASES_PATH = Path(__file__).parent / "evaluation" / "manual_search_cases.json"


def load_cases(path: Path) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("frozen_threshold") != DEFAULT_MIN_SIMILARITY:
        raise ValueError(
            "Evaluation threshold does not match the frozen application threshold."
        )
    cases = record.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Evaluation fixture must contain at least one case.")
    return record


def evaluate_cases(path: Path = DEFAULT_CASES_PATH) -> list[dict[str, Any]]:
    fixture = load_cases(path)
    top_k = fixture["top_k"]
    results = []

    for case in fixture["cases"]:
        response = search_manual(
            case["asset_id"],
            case["question"],
            top_k=top_k,
        )
        observed_section = (
            response["results"][0]["section"]["section_id"]
            if response["results"]
            else None
        )
        passed = (
            response["status"] == case["expected_status"]
            and observed_section == case["expected_section_id"]
        )
        results.append(
            {
                "id": case["id"],
                "phase": case["phase"],
                "category": case["category"],
                "passed": passed,
                "status": response["status"],
                "top_section_id": observed_section,
                "top_similarity": (
                    round(response["results"][0]["similarity"], 6)
                    if response["results"]
                    else None
                ),
            }
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    args = parser.parse_args()

    try:
        results = evaluate_cases(args.cases)
    except (OSError, ValueError) as error:
        parser.exit(1, f"error: {error}\n")

    for result in results:
        marker = "PASS" if result["passed"] else "FAIL"
        print(
            f"{marker} {result['phase']} {result['id']}: "
            f"{result['status']} {result['top_section_id']} "
            f"{result['top_similarity']}"
        )
    passed = sum(result["passed"] for result in results)
    print(f"Passed {passed}/{len(results)} retrieval cases.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
