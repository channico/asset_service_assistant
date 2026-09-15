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
                _chunk("MAN-LOW", [0.0, 1.0]),
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

    @patch("manual_tools.load_manual_index")
    def test_zero_embedding_has_zero_similarity(self, load_index) -> None:
        load_index.return_value = _index([_chunk("MAN-FORD", [1.0, 0.0])])

        result = search_manual(
            "VEH-1001",
            "door inspection",
            embed_texts=lambda texts, model: [[0.0, 0.0]],
            embedding_model="test-embedding-model",
        )

        self.assertEqual(result["results"][0]["similarity"], 0.0)

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

        self.assertEqual(result["status"], "found")
        self.assertEqual(result["results"], [])
        self.assertIn("No indexed manual passages", result["explanation"])


if __name__ == "__main__":
    unittest.main()
