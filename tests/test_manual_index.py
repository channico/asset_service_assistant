import json
import tempfile
import unittest
from pathlib import Path

from manual_index import (
    INDEX_FORMAT_VERSION,
    ManualIndexIncompatibleError,
    ManualIndexMissingError,
    ManualIndexStaleError,
    build_manual_index,
    load_manual_index,
)


def _write_manual(
    directory: Path,
    passage: str = "Inspect and record the result.",
) -> None:
    record = {
        "manual_id": "MAN-TEST-V1",
        "title": "Test Maintenance Guide",
        "manufacturer": "Ford",
        "applicable_model": "Transit",
        "version": "1.0",
        "version_status": "current",
        "sections": [
            {
                "section_id": "TEST-01",
                "title": "Inspection",
                "text": passage,
            }
        ],
    }
    (directory / "manual.json").write_text(json.dumps(record), encoding="utf-8")


def _fake_embedder(texts: list[str], model: str) -> list[list[float]]:
    del model
    return [[float(position), 1.0, 0.5] for position, _ in enumerate(texts, start=1)]


class ManualIndexTests(unittest.TestCase):
    def test_ingestion_persists_embeddings_and_required_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            manual_directory = directory / "manuals"
            manual_directory.mkdir()
            index_path = directory / "manual_index.json"
            _write_manual(manual_directory)

            index = build_manual_index(
                _fake_embedder,
                manual_directory=manual_directory,
                index_path=index_path,
            )

            persisted = json.loads(index_path.read_text(encoding="utf-8"))
            self.assertEqual(INDEX_FORMAT_VERSION, persisted["format_version"])
            self.assertEqual(index, persisted)
            self.assertEqual(persisted["chunks"][0]["embedding"], [1.0, 1.0, 0.5])
            metadata = persisted["chunks"][0]["metadata"]
            self.assertEqual(
                {
                    field: metadata[field]
                    for field in (
                        "document_title",
                        "section_id",
                        "section_title",
                        "version",
                        "version_status",
                        "manufacturer",
                        "applicable_model",
                    )
                },
                {
                    "document_title": "Test Maintenance Guide",
                    "section_id": "TEST-01",
                    "section_title": "Inspection",
                    "version": "1.0",
                    "version_status": "current",
                    "manufacturer": "Ford",
                    "applicable_model": "Transit",
                },
            )

    def test_reingestion_replaces_index_with_current_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            manual_directory = directory / "manuals"
            manual_directory.mkdir()
            index_path = directory / "manual_index.json"
            _write_manual(manual_directory, "Original passage.")
            build_manual_index(_fake_embedder, manual_directory, index_path)

            _write_manual(manual_directory, "Updated passage from the current corpus.")
            build_manual_index(_fake_embedder, manual_directory, index_path)

            loaded = load_manual_index(index_path, manual_directory)
            self.assertEqual(
                loaded["chunks"][0]["text"],
                "Updated passage from the current corpus.",
            )

    def test_missing_index_has_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            with self.assertRaisesRegex(ManualIndexMissingError, "ingest"):
                load_manual_index(directory / "missing.json", directory)

    def test_changed_manual_makes_existing_index_stale(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            manual_directory = directory / "manuals"
            manual_directory.mkdir()
            index_path = directory / "manual_index.json"
            _write_manual(manual_directory)
            build_manual_index(_fake_embedder, manual_directory, index_path)

            _write_manual(manual_directory, "The source document changed.")

            with self.assertRaisesRegex(ManualIndexStaleError, "corpus changed"):
                load_manual_index(index_path, manual_directory)

    def test_different_model_or_chunking_is_incompatible(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            manual_directory = directory / "manuals"
            manual_directory.mkdir()
            index_path = directory / "manual_index.json"
            _write_manual(manual_directory)
            build_manual_index(_fake_embedder, manual_directory, index_path)

            with self.assertRaisesRegex(
                ManualIndexIncompatibleError, "embedding model"
            ):
                load_manual_index(
                    index_path,
                    manual_directory,
                    expected_embedding_model="different-model",
                )
            with self.assertRaisesRegex(
                ManualIndexIncompatibleError, "chunking settings"
            ):
                load_manual_index(
                    index_path,
                    manual_directory,
                    max_words=60,
                )

    def test_wrong_format_version_is_incompatible(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            manual_directory = directory / "manuals"
            manual_directory.mkdir()
            index_path = directory / "manual_index.json"
            _write_manual(manual_directory)
            build_manual_index(_fake_embedder, manual_directory, index_path)
            index = json.loads(index_path.read_text(encoding="utf-8"))
            index["format_version"] = INDEX_FORMAT_VERSION + 1
            index_path.write_text(json.dumps(index), encoding="utf-8")

            with self.assertRaisesRegex(ManualIndexIncompatibleError, "format"):
                load_manual_index(index_path, manual_directory)

    def test_embedding_calls_are_injected_and_batch_all_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            manual_directory = directory / "manuals"
            manual_directory.mkdir()
            index_path = directory / "manual_index.json"
            _write_manual(manual_directory, "one two three four five six")
            calls: list[tuple[list[str], str]] = []

            def recording_embedder(texts: list[str], model: str) -> list[list[float]]:
                calls.append((texts, model))
                return [[1.0, 0.0] for _ in texts]

            index = build_manual_index(
                recording_embedder,
                manual_directory,
                index_path,
                max_words=3,
                overlap_words=1,
            )

            self.assertEqual(len(calls), 1)
            self.assertEqual(len(index["chunks"]), len(calls[0][0]))
            self.assertEqual(len(index["chunks"]), 3)
            self.assertTrue(
                all("Test Maintenance Guide" in text for text in calls[0][0])
            )


if __name__ == "__main__":
    unittest.main()
