"""Build and validate a persistent embedding index for maintenance manuals."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from manual_repository import DEFAULT_MANUAL_DIRECTORY, MaintenanceManual, load_manuals


DEFAULT_INDEX_PATH = Path(__file__).parent / "data" / "manual_index.json"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
INDEX_FORMAT_VERSION = 1
DEFAULT_MAX_WORDS = 120
DEFAULT_OVERLAP_WORDS = 20

EmbeddingFunction = Callable[[list[str], str], Sequence[Sequence[float]]]


class ManualIndexError(ValueError):
    """Base error for a missing, stale, or incompatible manual index."""


class ManualIndexMissingError(ManualIndexError):
    """Raised when the generated manual index does not exist."""


class ManualIndexStaleError(ManualIndexError):
    """Raised when manual source files changed after ingestion."""


class ManualIndexIncompatibleError(ManualIndexError):
    """Raised when index data or settings cannot be used by this application."""


def _chunking_settings(max_words: int, overlap_words: int) -> dict[str, Any]:
    if isinstance(max_words, bool) or not isinstance(max_words, int) or max_words < 1:
        raise ValueError("max_words must be a positive integer")
    if (
        isinstance(overlap_words, bool)
        or not isinstance(overlap_words, int)
        or overlap_words < 0
        or overlap_words >= max_words
    ):
        raise ValueError("overlap_words must be an integer from 0 to max_words - 1")
    return {
        "strategy": "section_words",
        "max_words": max_words,
        "overlap_words": overlap_words,
        "embedding_text_includes_titles": True,
    }


def _source_fingerprints(directory: Path) -> dict[str, str]:
    """Hash every source file so additions, edits, and deletions are detectable."""
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.glob("*.json"))
    }


def _section_passages(
    text: str,
    max_words: int,
    overlap_words: int,
) -> list[str]:
    words = text.split()
    step = max_words - overlap_words
    passages = []
    start = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        passages.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += step
    return passages


def _chunk_records(
    manuals: list[MaintenanceManual],
    max_words: int,
    overlap_words: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    embedding_inputs: list[str] = []

    for manual in manuals:
        for section in manual.sections:
            passages = _section_passages(section.text, max_words, overlap_words)
            for position, passage in enumerate(passages, start=1):
                records.append(
                    {
                        "chunk_id": (
                            f"{manual.manual_id}:{section.section_id}:{position}"
                        ),
                        "text": passage,
                        "metadata": {
                            "manual_id": manual.manual_id,
                            "document_title": manual.title,
                            "section_id": section.section_id,
                            "section_title": section.title,
                            "version": manual.version,
                            "version_status": manual.version_status,
                            "manufacturer": manual.manufacturer,
                            "applicable_model": manual.applicable_model,
                            "source_file": manual.source_file,
                            "section_chunk": position,
                            "section_chunk_count": len(passages),
                        },
                    }
                )
                embedding_inputs.append(
                    f"{manual.title}\n{section.title}\n{passage}"
                )

    return records, embedding_inputs


def _normalise_embeddings(
    embeddings: Sequence[Sequence[float]],
    expected_count: int,
) -> list[list[float]]:
    if len(embeddings) != expected_count:
        raise ManualIndexError(
            "Embedding provider returned "
            f"{len(embeddings)} vectors for {expected_count} chunks"
        )

    normalised: list[list[float]] = []
    dimensions: int | None = None
    for embedding in embeddings:
        vector = list(embedding)
        if not vector or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in vector
        ):
            raise ManualIndexError(
                "Embedding provider returned an empty or non-numeric vector"
            )
        if dimensions is None:
            dimensions = len(vector)
        elif len(vector) != dimensions:
            raise ManualIndexError(
                "Embedding provider returned vectors with inconsistent dimensions"
            )
        normalised.append([float(value) for value in vector])

    return normalised


def build_manual_index(
    embed_texts: EmbeddingFunction,
    manual_directory: Path = DEFAULT_MANUAL_DIRECTORY,
    index_path: Path = DEFAULT_INDEX_PATH,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    max_words: int = DEFAULT_MAX_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
) -> dict[str, Any]:
    """Load, chunk, embed, and atomically persist the current manual corpus."""
    settings = _chunking_settings(max_words, overlap_words)
    if not isinstance(embedding_model, str) or not embedding_model.strip():
        raise ValueError("embedding_model must be a non-empty string")

    manuals = load_manuals(manual_directory)
    records, embedding_inputs = _chunk_records(manuals, max_words, overlap_words)
    embeddings = _normalise_embeddings(
        embed_texts(embedding_inputs, embedding_model),
        len(records),
    )
    for record, embedding in zip(records, embeddings, strict=True):
        record["embedding"] = embedding

    index: dict[str, Any] = {
        "format_version": INDEX_FORMAT_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "embedding_model": embedding_model,
        "embedding_dimensions": len(embeddings[0]),
        "chunking": settings,
        "source_fingerprints": _source_fingerprints(manual_directory),
        "chunks": records,
    }

    index_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=index_path.parent,
            prefix=f".{index_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_name = temporary_file.name
            json.dump(index, temporary_file, indent=2)
            temporary_file.write("\n")
        Path(temporary_name).replace(index_path)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)

    return index


def _validate_index_records(index: dict[str, Any]) -> None:
    chunks = index.get("chunks")
    dimensions = index.get("embedding_dimensions")
    if not isinstance(chunks, list) or not chunks:
        raise ManualIndexIncompatibleError(
            "Manual index has no chunk records. Rebuild it with the ingest command."
        )
    if (
        isinstance(dimensions, bool)
        or not isinstance(dimensions, int)
        or dimensions < 1
    ):
        raise ManualIndexIncompatibleError(
            "Manual index has invalid embedding dimension metadata. Rebuild it."
        )

    required_metadata = {
        "manual_id",
        "document_title",
        "section_id",
        "section_title",
        "version",
        "version_status",
        "manufacturer",
        "applicable_model",
        "source_file",
    }
    for chunk in chunks:
        if not isinstance(chunk, dict):
            raise ManualIndexIncompatibleError("Manual index contains an invalid chunk")
        metadata = chunk.get("metadata")
        embedding = chunk.get("embedding")
        metadata_is_complete = isinstance(metadata, dict) and all(
            isinstance(metadata.get(field), str) and metadata[field].strip()
            for field in required_metadata
        )
        embedding_is_valid = (
            isinstance(embedding, list)
            and len(embedding) == dimensions
            and all(
                not isinstance(value, bool)
                and isinstance(value, (int, float))
                and math.isfinite(value)
                for value in embedding
            )
        )
        if (
            not metadata_is_complete
            or not isinstance(chunk.get("chunk_id"), str)
            or not chunk["chunk_id"].strip()
            or not isinstance(chunk.get("text"), str)
            or not chunk["text"].strip()
            or not embedding_is_valid
        ):
            raise ManualIndexIncompatibleError(
                "Manual index contains incomplete chunk metadata or embeddings. "
                "Rebuild it."
            )


def load_manual_index(
    index_path: Path = DEFAULT_INDEX_PATH,
    manual_directory: Path = DEFAULT_MANUAL_DIRECTORY,
    expected_embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    max_words: int = DEFAULT_MAX_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
) -> dict[str, Any]:
    """Load an index only when its format, settings, and sources remain current."""
    if not index_path.is_file():
        raise ManualIndexMissingError(
            f"Manual index not found at '{index_path}'. "
            "Run 'python manual_index.py ingest' first."
        )

    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ManualIndexIncompatibleError(
            "Manual index is unreadable or invalid JSON. "
            "Rebuild it with the ingest command."
        ) from error
    if not isinstance(index, dict):
        raise ManualIndexIncompatibleError(
            "Manual index root must be a JSON object. Rebuild it."
        )

    if index.get("format_version") != INDEX_FORMAT_VERSION:
        raise ManualIndexIncompatibleError(
            "Manual index format is incompatible with this application. Rebuild it."
        )
    if index.get("embedding_model") != expected_embedding_model:
        raise ManualIndexIncompatibleError(
            "Manual index embedding model does not match the configured model. "
            "Rebuild it."
        )
    if index.get("chunking") != _chunking_settings(max_words, overlap_words):
        raise ManualIndexIncompatibleError(
            "Manual index chunking settings do not match the configured settings. "
            "Rebuild it."
        )

    current_fingerprints = _source_fingerprints(manual_directory)
    if index.get("source_fingerprints") != current_fingerprints:
        raise ManualIndexStaleError(
            "Manual index is stale because the manual corpus changed. "
            "Run 'python manual_index.py ingest' to rebuild it."
        )

    _validate_index_records(index)
    return index


def embed_with_openai(texts: list[str], model: str) -> list[list[float]]:
    """Embed texts with OpenAI while keeping API concerns outside index logic."""
    try:
        from dotenv import load_dotenv
        from openai import OpenAI
    except ImportError as error:
        raise ManualIndexError(
            "OpenAI dependencies are not installed. Run 'python -m pip install -e .'."
        ) from error

    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        raise ManualIndexError(
            "OPENAI_API_KEY is not configured. Add it to the local .env file."
        )

    try:
        response = OpenAI().embeddings.create(input=texts, model=model)
    except Exception as error:
        raise ManualIndexError(
            "Embedding request failed. Check the API key, project access, "
            "and connection."
        ) from error

    ordered = sorted(response.data, key=lambda item: item.index)
    return [list(item.embedding) for item in ordered]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("ingest", "check"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument(
            "--manual-directory", type=Path, default=DEFAULT_MANUAL_DIRECTORY
        )
        subparser.add_argument("--index", type=Path, default=DEFAULT_INDEX_PATH)
        subparser.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL)
        subparser.add_argument("--max-words", type=int, default=DEFAULT_MAX_WORDS)
        subparser.add_argument(
            "--overlap-words", type=int, default=DEFAULT_OVERLAP_WORDS
        )

    args = parser.parse_args(argv)
    try:
        if args.command == "ingest":
            index = build_manual_index(
                embed_with_openai,
                manual_directory=args.manual_directory,
                index_path=args.index,
                embedding_model=args.model,
                max_words=args.max_words,
                overlap_words=args.overlap_words,
            )
            print(f"Indexed {len(index['chunks'])} manual chunks at '{args.index}'.")
        else:
            index = load_manual_index(
                index_path=args.index,
                manual_directory=args.manual_directory,
                expected_embedding_model=args.model,
                max_words=args.max_words,
                overlap_words=args.overlap_words,
            )
            print(f"Manual index is current with {len(index['chunks'])} chunks.")
    except ValueError as error:
        parser.exit(1, f"error: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
