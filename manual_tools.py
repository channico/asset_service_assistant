"""Grounded semantic search over manuals for one exact asset model."""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from asset_tools import get_asset_details
from manual_index import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_INDEX_PATH,
    DEFAULT_MANUAL_DIRECTORY,
    EmbeddingFunction,
    ManualIndexError,
    embed_with_openai,
    load_manual_index,
)


def _empty_response(
    status: str,
    error_code: str,
    message: str,
    asset: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a stable structured error response for manual search."""
    return {
        "status": status,
        "asset": asset,
        "results": [],
        "returned_count": 0,
        "candidate_count": 0,
        "explanation": None,
        "error": {"code": error_code, "message": message},
    }


def _normalise_query_embedding(
    embeddings: Sequence[Sequence[float]],
    expected_dimensions: int,
) -> list[float]:
    """Validate the single vector returned for a search question."""
    if len(embeddings) != 1:
        raise ManualIndexError(
            "Embedding provider must return exactly one vector for the question."
        )

    vector = list(embeddings[0])
    if len(vector) != expected_dimensions or any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        for value in vector
    ):
        raise ManualIndexError(
            "Question embedding does not match the manual index dimensions."
        )
    return [float(value) for value in vector]


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Calculate cosine similarity, treating a zero vector as no similarity."""
    left_magnitude = math.sqrt(sum(value * value for value in left))
    right_magnitude = math.sqrt(sum(value * value for value in right))
    left_is_zero = math.isclose(left_magnitude, 0.0, abs_tol=1e-12)
    right_is_zero = math.isclose(right_magnitude, 0.0, abs_tol=1e-12)
    if left_is_zero or right_is_zero:
        return 0.0

    similarity = sum(a * b for a, b in zip(left, right, strict=True)) / (
        left_magnitude * right_magnitude
    )
    return max(-1.0, min(1.0, similarity))


def _asset_identity(asset_record: dict[str, Any]) -> dict[str, str]:
    return {
        "asset_id": asset_record["asset_id"],
        "manufacturer": asset_record["manufacturer"],
        "model": asset_record["model"],
    }


def search_manual(
    asset_id: object,
    question: object,
    *,
    embed_texts: EmbeddingFunction = embed_with_openai,
    index_path: Path = DEFAULT_INDEX_PATH,
    manual_directory: Path = DEFAULT_MANUAL_DIRECTORY,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
) -> dict[str, Any]:
    """Return ranked manual passages applicable to one exact stored asset.

    Manufacturer and model filtering happens before the question is embedded
    and before any similarity is calculated. The function deliberately does
    not apply an abstention threshold; calibration belongs to the next lesson.
    """
    asset_result = get_asset_details(asset_id)
    if asset_result["status"] == "not_found":
        return _empty_response(
            "not_found",
            asset_result["error"]["code"],
            asset_result["error"]["message"],
        )

    asset = _asset_identity(asset_result["asset"])
    if not isinstance(question, str) or not question.strip():
        return _empty_response(
            "invalid_request",
            "invalid_question",
            "Question must be non-empty text.",
            asset,
        )

    try:
        index = load_manual_index(
            index_path=index_path,
            manual_directory=manual_directory,
            expected_embedding_model=embedding_model,
        )
    except ManualIndexError as error:
        return _empty_response(
            "unavailable",
            "manual_index_unavailable",
            str(error),
            asset,
        )

    manufacturer = asset["manufacturer"].strip().casefold()
    model = asset["model"].strip().casefold()
    candidates = [
        chunk
        for chunk in index["chunks"]
        if chunk["metadata"]["manufacturer"].strip().casefold() == manufacturer
        and chunk["metadata"]["applicable_model"].strip().casefold() == model
    ]
    if not candidates:
        return {
            "status": "found",
            "asset": asset,
            "results": [],
            "returned_count": 0,
            "candidate_count": 0,
            "explanation": (
                "No indexed manual passages apply to "
                f"{asset['manufacturer']} {asset['model']}."
            ),
            "error": None,
        }

    try:
        query_embedding = _normalise_query_embedding(
            embed_texts([question.strip()], index["embedding_model"]),
            index["embedding_dimensions"],
        )
    except ManualIndexError as error:
        return _empty_response(
            "unavailable",
            "manual_search_unavailable",
            str(error),
            asset,
        )

    results = []
    for chunk in candidates:
        metadata = chunk["metadata"]
        is_current = metadata["version_status"] == "current"
        results.append(
            {
                "document": {
                    "manual_id": metadata["manual_id"],
                    "title": metadata["document_title"],
                    "source_file": metadata["source_file"],
                },
                "section": {
                    "section_id": metadata["section_id"],
                    "title": metadata["section_title"],
                },
                "version": {
                    "number": metadata["version"],
                    "status": metadata["version_status"],
                    "label": (
                        "CURRENT"
                        if is_current
                        else "SUPERSEDED - DO NOT TREAT AS CURRENT GUIDANCE"
                    ),
                    "is_current": is_current,
                },
                "passage": chunk["text"],
                "similarity": _cosine_similarity(
                    query_embedding,
                    chunk["embedding"],
                ),
            }
        )

    results.sort(
        key=lambda result: (
            -result["similarity"],
            result["document"]["manual_id"].casefold(),
            result["section"]["section_id"].casefold(),
            result["passage"].casefold(),
        )
    )
    return {
        "status": "found",
        "asset": asset,
        "results": results,
        "returned_count": len(results),
        "candidate_count": len(candidates),
        "explanation": None,
        "error": None,
    }
