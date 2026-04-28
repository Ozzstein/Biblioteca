from __future__ import annotations

from datetime import UTC, datetime

from llm_rag.schemas.provenance import DocType, DocumentManifest


def _manifest(doc_type: str) -> DocumentManifest:
    return DocumentManifest(
        doc_id="papers/test-001",
        source_path="raw/papers/test-001.md",
        content_hash="sha256:abc123",
        doc_type=doc_type,
        source_connector="manual",
        fetched_at=datetime.now(UTC),
        last_processed=datetime.now(UTC),
    )


def test_doc_type_aliases_map_to_enum_values() -> None:
    assert _manifest("papers").doc_type == DocType.PAPER
    assert _manifest("reports").doc_type == DocType.REPORT
    assert _manifest("meetings").doc_type == DocType.MEETING
    assert _manifest("sop").doc_type == DocType.SOP


def test_doc_type_unknown_fallback() -> None:
    assert _manifest("dataset").doc_type == DocType.UNKNOWN
    assert _manifest("simulations").doc_type == DocType.UNKNOWN
    assert _manifest("anything-else").doc_type == DocType.UNKNOWN


def test_doc_type_serializes_as_string() -> None:
    payload = _manifest("paper").model_dump(mode="json")
    assert payload["doc_type"] == "paper"
