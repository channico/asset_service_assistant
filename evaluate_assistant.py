"""Run repeatable, assistant-level evaluations for the learning POC."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from dotenv import load_dotenv

from assistant_agent import AssistantResult, run_assistant


DEFAULT_CASES_PATH = Path(__file__).parent / "evaluation" / "assistant_cases.json"
STANDARD_SECTIONS = (
    "## Asset identity",
    "## Confirmed history",
    "## Manual guidance",
    "## Missing information and uncertainty",
)
EMPTY_MARKERS = {
    "asset_identity": "No validated asset identity was retrieved.",
    "confirmed_history": "No confirmed maintenance or ticket history was retrieved.",
    "manual_guidance": "No current, citable manual guidance was retrieved.",
    "evidence_gap": "No evidence gaps or unresolved uncertainty were identified.",
}


@dataclass(frozen=True)
class CaseResult:
    """One observed assistant run and its deterministic expectation failures."""

    case_id: str
    category: str
    passed: bool
    failures: tuple[str, ...]
    tool_calls: tuple[str, ...]
    limitations: tuple[str, ...]
    answer: str


def _require_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"{label} must be a list of non-empty strings.")
    return value


def load_cases(path: Path = DEFAULT_CASES_PATH) -> dict[str, Any]:
    """Load and validate the versioned assistant-evaluation fixture."""
    fixture = json.loads(path.read_text(encoding="utf-8"))
    if fixture.get("schema_version") != 1:
        raise ValueError("Assistant evaluation schema_version must be 1.")

    cases = fixture.get("cases")
    if not isinstance(cases, list) or len(cases) < 10:
        raise ValueError("Assistant evaluation must contain at least 10 cases.")

    identifiers: set[str] = set()
    categories: set[str] = set()
    required_categories = {"valid", "missing", "conflicting", "unsupported"}
    for index, case in enumerate(cases):
        label = f"cases[{index}]"
        if not isinstance(case, dict):
            raise ValueError(f"{label} must be an object.")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"{label}.id must be non-empty text.")
        if case_id in identifiers:
            raise ValueError(f"Duplicate assistant evaluation id: {case_id}")
        identifiers.add(case_id)

        category = case.get("category")
        question = case.get("question")
        if not isinstance(category, str) or not category.strip():
            raise ValueError(f"{label}.category must be non-empty text.")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"{label}.question must be non-empty text.")
        categories.add(category)

        tools = case.get("expected_tools")
        answer = case.get("expected_answer")
        if not isinstance(tools, dict) or not isinstance(answer, dict):
            raise ValueError(
                f"{label} must record expected_tools and expected_answer objects."
            )
        _require_string_list(tools.get("required"), f"{label}.required tools")
        _require_string_list(tools.get("forbidden"), f"{label}.forbidden tools")
        pairs = tools.get("ordered_pairs")
        if not isinstance(pairs, list) or not all(
            isinstance(pair, list)
            and len(pair) == 2
            and all(isinstance(item, str) and item for item in pair)
            for pair in pairs
        ):
            raise ValueError(f"{label}.ordered_pairs must contain tool-name pairs.")
        characteristics = answer.get("characteristics")
        _require_string_list(characteristics, f"{label}.characteristics")
        for key in ("required_text", "forbidden_text"):
            _require_string_list(answer.get(key, []), f"{label}.{key}")
        groups = answer.get("required_any_text", [])
        if not isinstance(groups, list) or not all(
            isinstance(group, list)
            and bool(group)
            and all(isinstance(item, str) and item.strip() for item in group)
            for group in groups
        ):
            raise ValueError(
                f"{label}.required_any_text must contain non-empty text groups."
            )

    missing_categories = required_categories - categories
    if missing_categories:
        raise ValueError(
            "Assistant evaluation is missing required categories: "
            + ", ".join(sorted(missing_categories))
        )
    return fixture


def _ordered_before(tool_calls: tuple[str, ...], first: str, second: str) -> bool:
    try:
        return tool_calls.index(first) < tool_calls.index(second)
    except ValueError:
        return False


def _check_presence(
    answer: str,
    expectations: dict[str, Any],
    key: str,
    marker: str,
) -> list[str]:
    expected = expectations.get(key, "any")
    if expected not in {"present", "absent", "any"}:
        return [f"invalid fixture expectation {key}={expected!r}"]
    is_present = marker not in answer
    if expected == "present" and not is_present:
        return [f"expected {key.replace('_', ' ')}"]
    if expected == "absent" and is_present:
        return [f"expected no {key.replace('_', ' ')}"]
    return []


def evaluate_result(case: dict[str, Any], result: AssistantResult) -> CaseResult:
    """Compare one assistant result with recorded routing and answer expectations."""
    failures: list[str] = []
    tool_calls = tuple(result.tool_calls)
    tools = case["expected_tools"]
    for tool_name in tools["required"]:
        if tool_name not in tool_calls:
            failures.append(f"required tool was not called: {tool_name}")
    for tool_name in tools["forbidden"]:
        if tool_name in tool_calls:
            failures.append(f"forbidden tool was called: {tool_name}")
    for first, second in tools["ordered_pairs"]:
        if not _ordered_before(tool_calls, first, second):
            failures.append(f"expected {first} before {second}")

    answer = result.answer
    expected_answer = case["expected_answer"]
    if expected_answer.get("structured_sections", True):
        for section in STANDARD_SECTIONS:
            if section not in answer:
                failures.append(f"missing structured answer section: {section}")

    for key, marker in EMPTY_MARKERS.items():
        failures.extend(_check_presence(answer, expected_answer, key, marker))

    escalation = expected_answer.get("escalation", "any")
    if escalation == "present" and "## Escalation" not in answer:
        failures.append("expected escalation")
    elif escalation == "absent" and "## Escalation" in answer:
        failures.append("expected no escalation")
    elif escalation not in {"present", "absent", "any"}:
        failures.append(f"invalid fixture expectation escalation={escalation!r}")

    if expected_answer.get("current_citation") is True:
        if "  - Source:" not in answer or "[CURRENT]" not in answer:
            failures.append("expected a complete current-manual citation")
    if expected_answer.get("qualified_review") is True:
        if "**Qualified review:**" not in answer:
            failures.append("expected qualified review guidance")

    folded_answer = answer.casefold()
    for text in expected_answer.get("required_text", []):
        if text.casefold() not in folded_answer:
            failures.append(f"required answer text was absent: {text}")
    for group in expected_answer.get("required_any_text", []):
        if not any(text.casefold() in folded_answer for text in group):
            failures.append("answer contained none of: " + ", ".join(group))
    for text in expected_answer.get("forbidden_text", []):
        if text.casefold() in folded_answer:
            failures.append(f"forbidden answer text was present: {text}")
    if "assistant could not complete" in folded_answer:
        failures.append("agent run failed instead of producing an evaluated answer")

    return CaseResult(
        case_id=case["id"],
        category=case["category"],
        passed=not failures,
        failures=tuple(failures),
        tool_calls=tool_calls,
        limitations=tuple(result.limitations),
        answer=answer,
    )


RunnerFunction = Callable[..., AssistantResult]


def evaluate_cases(
    cases: Iterable[dict[str, Any]],
    *,
    model: str,
    runner: RunnerFunction = run_assistant,
) -> list[CaseResult]:
    """Run selected cases through the real assistant or an injected test runner."""
    return [
        evaluate_result(case, runner(case["question"], model=model))
        for case in cases
    ]


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument(
        "--case",
        action="append",
        dest="case_ids",
        help="Run only this case ID; repeat the option to select several cases.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("ASA_AGENT_MODEL"),
        help="Explicit model identifier, or set ASA_AGENT_MODEL.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Optional path for a machine-readable result report.",
    )
    args = parser.parse_args()

    if not args.model:
        parser.error("--model or ASA_AGENT_MODEL is required for reproducible runs")

    try:
        fixture = load_cases(args.cases)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"error: {error}\n")

    cases = fixture["cases"]
    if args.case_ids:
        selected = set(args.case_ids)
        known = {case["id"] for case in cases}
        unknown = selected - known
        if unknown:
            parser.error("unknown case ID(s): " + ", ".join(sorted(unknown)))
        cases = [case for case in cases if case["id"] in selected]

    results = evaluate_cases(cases, model=args.model)
    for result in results:
        marker = "PASS" if result.passed else "FAIL"
        calls = ", ".join(result.tool_calls) or "none"
        print(f"{marker} {result.case_id} [{result.category}] tools={calls}")
        for failure in result.failures:
            print(f"  - {failure}")

    passed = sum(result.passed for result in results)
    print(f"Passed {passed}/{len(results)} assistant evaluation cases.")

    if args.json_output is not None:
        report = {
            "schema_version": 1,
            "model": args.model,
            "cases_file": str(args.cases),
            "passed": passed,
            "total": len(results),
            "results": [asdict(result) for result in results],
        }
        args.json_output.write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
