import unittest
from unittest.mock import patch

from manual_tools import search_manual


def _chunk(
    manual_id: str,
    similarity_vector: list[float],
    *,
    manufacturer: str = "Ford",
    model: str = "Transit",
    version: str = "2.0",
    version_status: str = "current",
) -> dict[str, object]:
    return {
        "chunk_id": f"{manual_id}:CHECK-01:1",
        "text": f"Evidence from {manual_id}.",
        "metadata": {
            "manual_id": manual_id,
            "document_title": f"{model} Maintenance Guide",
            "section_id": "CHECK-01",
            "section_title": "Inspection check",
            "version": version,
            "version_status": version_status,
            "manufacturer": manufacturer,
            "applicable_model": model,
            "source_file": f"{manual_id.lower()}.json",
        },
        "embedding": similarity_vector,
    }


def _index(chunks: list[dict[str, object]]) -> dict[str, object]:
    return {
        "embedding_model": "test-embedding-model",
        "embedding_dimensions": 2,
        "chunks": chunks,
    }


class ManualSearchTests(unittest.TestCase):
    @patch("manual_tools.load_manual_index")
    def test_filters_by_manufacturer_and_model_before_ranking(self, load_index) -> None:
        load_index.return_value = _index(
            [
                _chunk("MAN-FORD", [0.5, 0.5]),
                _chunk(
                    "MAN-WRONG-MAKE",
                    [1.0, 0.0],
                    manufacturer="Toyota",
                    model="Transit",
                ),
                _chunk(
                    "MAN-WRONG-MODEL",
                    [1.0, 0.0],
                    manufacturer="Ford",
                    model="8FG25",
                ),
            ]
        )

        result = search_manual(
            "VEH-1001",
            "How should I inspect it?",
            embed_texts=lambda texts, model: [[1.0, 0.0]],
            embedding_model="test-embedding-model",
        )

        self.assertEqual(result["status"], "found")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(
            [item["document"]["manual_id"] for item in result["results"]],
            ["MAN-FORD"],
        )

    @patch("manual_tools.load_manual_index")
    def test_results_are_sorted_by_descending_cosine_similarity(self, load_index) -> None:
        load_index.return_value = _index(
            [
                _chunk("MAN-MIDDLE", [0.8, 0.6]),
                _chunk("MAN-LOW", [0.5, 0.866025]),
                _chunk("MAN-HIGH", [1.0, 0.0]),
            ]
        )

        result = search_manual(
            "VEH-1001",
            "door inspection",
            embed_texts=lambda texts, model: [[1.0, 0.0]],
            embedding_model="test-embedding-model",
        )

        self.assertEqual(
            [item["document"]["manual_id"] for item in result["results"]],
            ["MAN-HIGH", "MAN-MIDDLE", "MAN-LOW"],
        )
        similarities = [item["similarity"] for item in result["results"]]
        self.assertEqual(similarities, sorted(similarities, reverse=True))

    def test_zero_embedding_has_zero_similarity(self) -> None:
        from manual_tools import _cosine_similarity

        self.assertEqual(_cosine_similarity([0.0, 0.0], [1.0, 0.0]), 0.0)

    @patch("manual_tools.load_manual_index")
    def test_scores_and_sorts_before_threshold_and_top_k(self, load_index) -> None:
        load_index.return_value = _index(
            [
                _chunk("MAN-LOW", [0.3, 0.953939]),
                _chunk("MAN-HIGH", [0.9, 0.43589]),
                _chunk("MAN-MIDDLE", [0.7, 0.714143]),
            ]
        )

        result = search_manual(
            "VEH-1001",
            "door inspection",
            embed_texts=lambda texts, model: [[1.0, 0.0]],
            embedding_model="test-embedding-model",
            top_k=1,
        )

        self.assertEqual(result["candidate_count"], 3)
        self.assertEqual(result["returned_count"], 1)
        self.assertEqual(result["results"][0]["document"]["manual_id"], "MAN-HIGH")

    @patch("manual_tools.load_manual_index")
    def test_unsupported_question_abstains_without_citations(self, load_index) -> None:
        load_index.return_value = _index(
            [
                _chunk("MAN-FORD-CURRENT", [0.39, 0.920815]),
                _chunk("MAN-FORD-OLD", [0.2, 0.979796]),
            ]
        )

        result = search_manual(
            "VEH-1001",
            "Which engine oil viscosity should I use?",
            embed_texts=lambda texts, model: [[1.0, 0.0]],
            embedding_model="test-embedding-model",
        )

        self.assertEqual(result["status"], "abstained")
        self.assertEqual(result["results"], [])
        self.assertEqual(result["returned_count"], 0)
        self.assertEqual(result["candidate_count"], 2)
        self.assertIn("No citation can be provided", result["explanation"])

    @patch("manual_tools.load_manual_index")
    def test_wrong_model_question_abstains_after_model_filtering(self, load_index) -> None:
        load_index.return_value = _index(
            [
                _chunk("MAN-FORD", [0.38, 0.924986]),
                _chunk(
                    "MAN-TOYOTA",
                    [1.0, 0.0],
                    manufacturer="Toyota",
                    model="8FG25",
                ),
            ]
        )

        result = search_manual(
            "VEH-1001",
            "How do I inspect forklift forks?",
            embed_texts=lambda texts, model: [[1.0, 0.0]],
            embedding_model="test-embedding-model",
        )

        self.assertEqual(result["status"], "abstained")
        self.assertEqual(result["results"], [])
        self.assertEqual(result["candidate_count"], 1)

    @patch("manual_tools.load_manual_index")
    def test_results_include_citations_evidence_and_clear_version_labels(
        self, load_index
    ) -> None:
        load_index.return_value = _index(
            [
                _chunk("MAN-CURRENT", [1.0, 0.0]),
                _chunk(
                    "MAN-OLD",
                    [0.5, 0.5],
                    version="1.0",
                    version_status="superseded",
                ),
            ]
        )

        result = search_manual(
            "VEH-1001",
            "door inspection",
            embed_texts=lambda texts, model: [[1.0, 0.0]],
            embedding_model="test-embedding-model",
        )

        current, superseded = result["results"]
        for item in result["results"]:
            self.assertEqual(
                set(item),
                {"document", "section", "version", "passage", "similarity"},
            )
            self.assertIn("manual_id", item["document"])
            self.assertIn("section_id", item["section"])
        self.assertEqual(current["version"]["label"], "CURRENT")
        self.assertTrue(current["version"]["is_current"])
        self.assertEqual(superseded["version"]["status"], "superseded")
        self.assertIn("DO NOT TREAT AS CURRENT", superseded["version"]["label"])
        self.assertFalse(superseded["version"]["is_current"])

    def test_unknown_asset_returns_structured_error_without_embedding(self) -> None:
        def unexpected_embed(texts, model):
            self.fail("Unknown assets must not be embedded")

        result = search_manual(
            "VEH-9999",
            "door inspection",
            embed_texts=unexpected_embed,
        )

        self.assertEqual(result["status"], "not_found")
        self.assertEqual(result["results"], [])
        self.assertEqual(result["error"]["code"], "asset_not_found")

    def test_malformed_asset_returns_structured_error(self) -> None:
        result = search_manual("VEH-100", "door inspection")

        self.assertEqual(result["status"], "not_found")
        self.assertEqual(result["results"], [])
        self.assertEqual(result["error"]["code"], "malformed_asset_id")

    def test_invalid_question_returns_structured_error(self) -> None:
        for question in (None, "", "   ", 42):
            with self.subTest(question=question):
                result = search_manual("VEH-1001", question)

                self.assertEqual(result["status"], "invalid_request")
                self.assertEqual(result["results"], [])
                self.assertEqual(result["error"]["code"], "invalid_question")

    def test_invalid_retrieval_settings_return_structured_errors(self) -> None:
        cases = [
            ({"top_k": 0}, "invalid_top_k"),
            ({"top_k": True}, "invalid_top_k"),
        ]
        for arguments, error_code in cases:
            with self.subTest(arguments=arguments):
                result = search_manual("VEH-1001", "door inspection", **arguments)

                self.assertEqual(result["status"], "invalid_request")
                self.assertEqual(result["error"]["code"], error_code)

    @patch("manual_tools.load_manual_index")
    def test_question_embedding_is_deterministic_and_injected(self, load_index) -> None:
        load_index.return_value = _index([_chunk("MAN-FORD", [1.0, 0.0])])
        calls = []

        def recording_embedder(texts, model):
            calls.append((texts, model))
            return [[1.0, 0.0]]

        search_manual(
            "VEH-1001",
            "  inspect the door  ",
            embed_texts=recording_embedder,
            embedding_model="test-embedding-model",
        )

        self.assertEqual(calls, [(["inspect the door"], "test-embedding-model")])

    @patch("manual_tools.load_manual_index")
    def test_asset_without_applicable_manual_returns_explained_empty_result(
        self, load_index
    ) -> None:
        load_index.return_value = _index([_chunk("MAN-FORD", [1.0, 0.0])])

        result = search_manual(
            "VEH-1002",
            "inspection",
            embed_texts=lambda texts, model: self.fail(
                "A question with no applicable candidates must not be embedded"
            ),
            embedding_model="test-embedding-model",
        )

        self.assertEqual(result["status"], "abstained")
        self.assertEqual(result["results"], [])
        self.assertIn("No indexed manual passages", result["explanation"])


if __name__ == "__main__":
    unittest.main()
