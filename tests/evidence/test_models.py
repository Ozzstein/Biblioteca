"""Tests for canonical evidence-record schemas."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from llm_rag.evidence.models import (
    DocumentType,
    EvidenceChunk,
    EvidenceDocument,
    EvidenceStore,
    ProvenanceSpan,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_span(**overrides) -> ProvenanceSpan:
    defaults = {"start_byte": 0, "end_byte": 512}
    defaults.update(overrides)
    return ProvenanceSpan(**defaults)


def _make_document(**overrides) -> EvidenceDocument:
    defaults = {
        "doc_id": "papers/sample-lfp-001",
        "source_path": "raw/papers/sample-lfp-001.md",
        "doc_type": DocumentType.PAPER,
        "content_hash": "sha256:abc123",
        "ingested_at": datetime(2026, 4, 18, 10, 0, 0, tzinfo=timezone.utc),
    }
    defaults.update(overrides)
    return EvidenceDocument(**defaults)


def _make_chunk(index: int = 0, **overrides) -> EvidenceChunk:
    text = overrides.pop("text", f"Chunk text number {index}.")
    defaults = {
        "chunk_id": f"papers/sample-lfp-001:chunk-{index:03d}",
        "document_id": "papers/sample-lfp-001",
        "text": text,
        "content_hash": EvidenceChunk.hash_text(text),
        "span": _make_span(start_byte=index * 512, end_byte=(index + 1) * 512),
        "chunk_index": index,
        "token_estimate": len(text) // 4,
    }
    defaults.update(overrides)
    return EvidenceChunk(**defaults)


def _make_store(**overrides) -> EvidenceStore:
    doc = overrides.pop("document", _make_document())
    chunks = overrides.pop("chunks", [_make_chunk(0), _make_chunk(1)])
    return EvidenceStore(document=doc, chunks=chunks, **overrides)


# ---------------------------------------------------------------------------
# ProvenanceSpan
# ---------------------------------------------------------------------------

class TestProvenanceSpan:
    def test_valid_span(self):
        span = _make_span(start_byte=100, end_byte=200, page_start=1, page_end=3, section_name="Introduction")
        assert span.byte_length == 100
        assert span.page_start == 1
        assert span.page_end == 3
        assert span.section_name == "Introduction"

    def test_byte_length_property(self):
        span = _make_span(start_byte=0, end_byte=1024)
        assert span.byte_length == 1024

    def test_end_byte_must_exceed_start_byte(self):
        with pytest.raises(ValidationError, match="end_byte.*must be greater than start_byte"):
            _make_span(start_byte=100, end_byte=100)

    def test_end_byte_less_than_start_byte(self):
        with pytest.raises(ValidationError, match="end_byte.*must be greater than start_byte"):
            _make_span(start_byte=200, end_byte=100)

    def test_negative_start_byte_rejected(self):
        with pytest.raises(ValidationError):
            _make_span(start_byte=-1, end_byte=10)

    def test_zero_end_byte_rejected(self):
        with pytest.raises(ValidationError):
            _make_span(start_byte=0, end_byte=0)

    def test_page_end_before_page_start_rejected(self):
        with pytest.raises(ValidationError, match="page_end.*must be >= page_start"):
            _make_span(page_start=5, page_end=3)

    def test_pages_optional(self):
        span = _make_span()
        assert span.page_start is None
        assert span.page_end is None
        assert span.section_name is None

    def test_same_page_start_and_end_ok(self):
        span = _make_span(page_start=3, page_end=3)
        assert span.page_start == span.page_end == 3


# ---------------------------------------------------------------------------
# EvidenceChunk
# ---------------------------------------------------------------------------

class TestEvidenceChunk:
    def test_hash_text_deterministic(self):
        text = "LFP shows 170 mAh/g theoretical capacity."
        h1 = EvidenceChunk.hash_text(text)
        h2 = EvidenceChunk.hash_text(text)
        assert h1 == h2
        assert h1.startswith("sha256:")

    def test_different_text_different_hash(self):
        h1 = EvidenceChunk.hash_text("alpha")
        h2 = EvidenceChunk.hash_text("beta")
        assert h1 != h2

    def test_empty_text_rejected(self):
        with pytest.raises(ValidationError):
            _make_chunk(text="")

    def test_chunk_serialization(self):
        chunk = _make_chunk(0)
        data = chunk.model_dump()
        assert data["chunk_id"] == "papers/sample-lfp-001:chunk-000"
        assert data["span"]["start_byte"] == 0
        assert data["span"]["end_byte"] == 512

    def test_optional_embedding(self):
        chunk = _make_chunk(0, embedding=[0.1, 0.2, 0.3])
        assert chunk.embedding == [0.1, 0.2, 0.3]

        chunk_no_emb = _make_chunk(0)
        assert chunk_no_emb.embedding is None

    def test_metadata_dict(self):
        chunk = _make_chunk(0, metadata={"language": "en"})
        assert chunk.metadata == {"language": "en"}


# ---------------------------------------------------------------------------
# EvidenceDocument
# ---------------------------------------------------------------------------

class TestEvidenceDocument:
    def test_valid_document(self):
        doc = _make_document(
            title="Capacity Fade in LFP",
            authors=["A. Researcher"],
            doi="10.1016/j.sample",
        )
        assert doc.doc_id == "papers/sample-lfp-001"
        assert doc.doc_type == DocumentType.PAPER
        assert doc.title == "Capacity Fade in LFP"
        assert doc.authors == ["A. Researcher"]
        assert doc.doi == "10.1016/j.sample"

    def test_empty_doc_id_rejected(self):
        with pytest.raises(ValidationError):
            _make_document(doc_id="")

    def test_empty_source_path_rejected(self):
        with pytest.raises(ValidationError):
            _make_document(source_path="")

    def test_document_type_enum(self):
        for dt in DocumentType:
            doc = _make_document(doc_type=dt)
            assert doc.doc_type == dt

    def test_optional_fields_default_none(self):
        doc = _make_document()
        assert doc.title is None
        assert doc.doi is None
        assert doc.arxiv_id is None
        assert doc.source_connector is None
        assert doc.page_count is None
        assert doc.byte_size is None

    def test_metadata_dict(self):
        doc = _make_document(metadata={"journal": "Nature Energy"})
        assert doc.metadata["journal"] == "Nature Energy"


# ---------------------------------------------------------------------------
# EvidenceStore
# ---------------------------------------------------------------------------

class TestEvidenceStore:
    def test_valid_store(self):
        store = _make_store()
        assert store.chunk_count == 2
        assert store.total_tokens > 0

    def test_chunk_ownership_validated(self):
        bad_chunk = _make_chunk(0, document_id="papers/wrong-doc")
        with pytest.raises(ValidationError, match="document_id"):
            _make_store(chunks=[bad_chunk])

    def test_get_chunk_found(self):
        store = _make_store()
        found = store.get_chunk("papers/sample-lfp-001:chunk-000")
        assert found is not None
        assert found.chunk_index == 0

    def test_get_chunk_not_found(self):
        store = _make_store()
        assert store.get_chunk("nonexistent") is None

    def test_empty_chunks_ok(self):
        store = _make_store(chunks=[])
        assert store.chunk_count == 0
        assert store.total_tokens == 0

    def test_total_tokens(self):
        c0 = _make_chunk(0, text="a" * 100)
        c1 = _make_chunk(1, text="b" * 200)
        store = _make_store(chunks=[c0, c1])
        assert store.total_tokens == (100 // 4) + (200 // 4)


# ---------------------------------------------------------------------------
# Serialization / Deserialization roundtrips
# ---------------------------------------------------------------------------

class TestRoundtrip:
    def test_provenance_span_roundtrip(self):
        span = _make_span(start_byte=10, end_byte=500, page_start=1, page_end=2, section_name="Methods")
        data = span.model_dump()
        restored = ProvenanceSpan(**data)
        assert restored == span

    def test_chunk_roundtrip_json(self):
        chunk = _make_chunk(0, embedding=[0.1, 0.2])
        json_str = chunk.model_dump_json()
        restored = EvidenceChunk.model_validate_json(json_str)
        assert restored == chunk

    def test_document_roundtrip_json(self):
        doc = _make_document(title="Test", authors=["X"], doi="10.1/x")
        json_str = doc.model_dump_json()
        restored = EvidenceDocument.model_validate_json(json_str)
        assert restored == doc

    def test_store_roundtrip_json(self):
        store = _make_store()
        json_str = store.to_json()
        restored = EvidenceStore.model_validate_json(json_str)
        assert restored.document == store.document
        assert restored.chunks == store.chunks
        assert restored.chunk_count == store.chunk_count

    def test_deterministic_serialization(self):
        """Same input must produce byte-identical JSON output."""
        store = _make_store()
        json1 = store.to_json()
        json2 = store.to_json()
        assert json1 == json2

    def test_store_json_is_valid_json(self):
        store = _make_store()
        parsed = json.loads(store.to_json())
        assert "document" in parsed
        assert "chunks" in parsed
        assert len(parsed["chunks"]) == 2
