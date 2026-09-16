import unittest

from pydantic import ValidationError

from service_answer import (
    AssetIdentity,
    ConfirmedFact,
    EvidenceGap,
    ManualCitation,
    ManualGuidance,
    ServiceAnswer,
    Uncertainty,
    add_context_limitations,
    ensure_required_escalation,
    render_service_answer,
    validate_manual_citations,
)


def current_citation() -> ManualCitation:
    return ManualCitation(
        manual_id="MAN-FORD-TRANSIT-02",
        manual_title="Ford Transit Maintenance Guide",
        section_id="door-track-inspection",
        section_title="Sliding Door Track Inspection",
        version="2.0",
        version_status="current",
        source_file="ford_transit_v2.json",
    )


def base_answer(**updates) -> ServiceAnswer:
    values = {
        "summary": "Evidence-based answer",
        "asset_identity": None,
        "confirmed_history": [],
        "manual_guidance": [],
        "missing_information": [],
        "uncertainties": [],
        "escalation": None,
    }
    values.update(updates)
    return ServiceAnswer(**values)


class ServiceAnswerSchemaTests(unittest.TestCase):
    def test_manual_guidance_cannot_exist_without_a_citation(self) -> None:
        with self.assertRaises(ValidationError):
            ManualGuidance(recommendation="Inspect the door track.", citations=[])

    def test_manual_citation_must_be_current(self) -> None:
        with self.assertRaises(ValidationError):
            ManualCitation(
                manual_id="MAN-1",
                manual_title="Old guide",
                section_id="SEC-1",
                section_title="Old section",
                version="1.0",
                version_status="superseded",
                source_file="old.json",
            )

    def test_rejects_manual_citation_not_returned_by_search(self) -> None:
        answer = base_answer(
            manual_guidance=[
                ManualGuidance(
                    recommendation="Inspect the door track.",
                    citations=[current_citation()],
                )
            ]
        )

        with self.assertRaisesRegex(ValueError, "not returned"):
            validate_manual_citations(answer, [])

    def test_accepts_exact_current_citation_returned_by_search(self) -> None:
        answer = base_answer(
            manual_guidance=[
                ManualGuidance(
                    recommendation="Inspect the door track.",
                    citations=[current_citation()],
                )
            ]
        )
        result = {
            "status": "found",
            "results": [
                {
                    "document": {
                        "manual_id": "MAN-FORD-TRANSIT-02",
                        "title": "Ford Transit Maintenance Guide",
                        "source_file": "ford_transit_v2.json",
                    },
                    "section": {
                        "section_id": "door-track-inspection",
                        "title": "Sliding Door Track Inspection",
                    },
                    "version": {"number": "2.0", "status": "current"},
                }
            ],
        }

        validate_manual_citations(answer, [("search_manual", result)])


class ServiceAnswerCompositionTests(unittest.TestCase):
    def test_renderer_separates_facts_guidance_gaps_and_citations(self) -> None:
        answer = base_answer(
            asset_identity=AssetIdentity(
                asset_id="VEH-1001",
                name="North Service Van",
                asset_type="service_van",
                manufacturer="Ford",
                model="Transit",
                year=2022,
                location="North Depot",
                recorded_status="active",
            ),
            confirmed_history=[
                ConfirmedFact(
                    source_type="maintenance_event",
                    source_id="MNT-0011",
                    statement="The sliding door track was serviced.",
                )
            ],
            manual_guidance=[
                ManualGuidance(
                    recommendation="Inspect the track for contamination.",
                    citations=[current_citation()],
                )
            ],
            missing_information=[
                EvidenceGap(
                    missing="No live inspection is available.",
                    impact="Current condition cannot be confirmed.",
                )
            ],
            uncertainties=[
                Uncertainty(
                    unresolved="The current fault cause is unknown.",
                    reason="Historical service does not diagnose the present symptom.",
                )
            ],
        )

        rendered = render_service_answer(answer)

        self.assertIn("## Asset identity", rendered)
        self.assertIn("## Confirmed history", rendered)
        self.assertIn("[maintenance_event: MNT-0011]", rendered)
        self.assertIn("## Manual guidance", rendered)
        self.assertIn("MAN-FORD-TRANSIT-02", rendered)
        self.assertIn("door-track-inspection", rendered)
        self.assertIn("version 2.0 [CURRENT]", rendered)
        self.assertIn("## Missing information and uncertainty", rendered)
        self.assertNotIn("## Escalation", rendered)

    def test_context_limitations_are_added_as_missing_evidence(self) -> None:
        answer = base_answer()

        updated = add_context_limitations(answer, ["Manual index unavailable."])

        self.assertEqual(
            updated.missing_information[0].missing,
            "Manual index unavailable.",
        )

    def test_safety_sensitive_question_forces_qualified_review(self) -> None:
        answer = base_answer()

        updated = ensure_required_escalation(
            "VEH-1001 has smoke near exposed electrical parts. Is it safe to use?",
            answer,
        )
        rendered = render_service_answer(updated)

        self.assertIsNotNone(updated.escalation)
        self.assertIn("## Escalation", rendered)
        self.assertIn("Stop using the asset", rendered)
        self.assertIn("qualified technician", rendered)

    def test_common_safety_wording_also_forces_review(self) -> None:
        answer = base_answer()

        for question in (
            "Fuel is leaking from VEH-1001.",
            "The brakes failed; can I keep driving?",
            "Can I disable the lockout/tagout control?",
        ):
            with self.subTest(question=question):
                updated = ensure_required_escalation(question, answer)
                self.assertIsNotNone(updated.escalation)

    def test_ordinary_question_does_not_add_escalation(self) -> None:
        answer = base_answer()

        updated = ensure_required_escalation(
            "Show the maintenance history for VEH-1001.",
            answer,
        )

        self.assertIsNone(updated.escalation)


if __name__ == "__main__":
    unittest.main()
