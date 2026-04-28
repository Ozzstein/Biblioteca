"""Tests for pipeline contract models."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from llm_rag.pipeline.contracts import (
    ClaimCandidate,
    EvidenceChunk,
    ExtractedEntity,
    ExtractedRelation,
    GraphPatch,
    QueryCitation,
    QueryResultBundle,
    SourceDocument,
    WikiPageDraft,
)
from llm_rag.pipeline.runner import (
    PipelineRunner,
    StageOutputValidationError,
    _extract_json,
    _matches_any_model,
)
from llm_rag.schemas.entities import EntityType, RelationType
from llm_rag.schemas.provenance import ProcessingStage

NOW = datetime(2026, 4, 24, 12, 0, 0, tzinfo=UTC)


# --- SourceDocument ---


class TestSourceDocument:
    def test_valid(self):
        doc = SourceDocument(
            doc_id="papers/lfp-001",
            source_path="raw/papers/lfp-001.md",
            doc_type="paper",
            content_hash="sha256:abc123",
            ingested_at=NOW,
        )
        assert doc.doc_id == "papers/lfp-001"
        assert doc.doc_type == "paper"

    def test_empty_doc_id_rejected(self):
        with pytest.raises(ValidationError):
            SourceDocument(
                doc_id="",
                source_path="raw/x.md",
                doc_type="paper",
                content_hash="sha256:abc",
                ingested_at=NOW,
            )

    def test_serialization(self):
        doc = SourceDocument(
            doc_id="papers/lfp-001",
            source_path="raw/papers/lfp-001.md",
            doc_type="paper",
            content_hash="sha256:abc123",
            ingested_at=NOW,
        )
        d = doc.model_dump()
        assert d["doc_id"] == "papers/lfp-001"
        json_str = doc.model_dump_json()
        assert "papers/lfp-001" in json_str


# --- EvidenceChunk ---


class TestEvidenceChunk:
    def test_valid(self):
        chunk = EvidenceChunk(
            document_id="papers/lfp-001",
            chunk_id="papers/lfp-001:c0",
            text="LFP shows 170 mAh/g capacity.",
            start_offset=0,
            end_offset=100,
        )
        assert chunk.embedding is None

    def test_with_embedding(self):
        chunk = EvidenceChunk(
            document_id="papers/lfp-001",
            chunk_id="papers/lfp-001:c0",
            text="Some text.",
            start_offset=0,
            end_offset=50,
            embedding=[0.1, 0.2, 0.3],
        )
        assert len(chunk.embedding) == 3

    def test_negative_start_offset_rejected(self):
        with pytest.raises(ValidationError):
            EvidenceChunk(
                document_id="papers/lfp-001",
                chunk_id="c0",
                text="text",
                start_offset=-1,
                end_offset=50,
            )

    def test_zero_end_offset_rejected(self):
        with pytest.raises(ValidationError):
            EvidenceChunk(
                document_id="papers/lfp-001",
                chunk_id="c0",
                text="text",
                start_offset=0,
                end_offset=0,
            )

    def test_empty_text_rejected(self):
        with pytest.raises(ValidationError):
            EvidenceChunk(
                document_id="papers/lfp-001",
                chunk_id="c0",
                text="",
                start_offset=0,
                end_offset=50,
            )


# --- ExtractedEntity ---


class TestExtractedEntity:
    def test_valid(self):
        entity = ExtractedEntity(
            entity_id="material:lfp",
            name="LFP",
            entity_type=EntityType.MATERIAL,
            aliases=["LiFePO4"],
            source_chunks=["papers/lfp-001:c0"],
            confidence=0.95,
        )
        assert entity.entity_type == EntityType.MATERIAL

    def test_confidence_above_one_rejected(self):
        with pytest.raises(ValidationError):
            ExtractedEntity(
                entity_id="material:lfp",
                name="LFP",
                entity_type=EntityType.MATERIAL,
                confidence=1.5,
            )

    def test_confidence_below_zero_rejected(self):
        with pytest.raises(ValidationError):
            ExtractedEntity(
                entity_id="material:lfp",
                name="LFP",
                entity_type=EntityType.MATERIAL,
                confidence=-0.1,
            )

    def test_serialization(self):
        entity = ExtractedEntity(
            entity_id="material:lfp",
            name="LFP",
            entity_type=EntityType.MATERIAL,
            confidence=0.9,
        )
        d = entity.model_dump()
        assert d["entity_type"] == "Material"
        assert d["confidence"] == 0.9


# --- ExtractedRelation ---


class TestExtractedRelation:
    def test_valid(self):
        rel = ExtractedRelation(
            relation_id="rel:001",
            subject_id="material:lfp",
            predicate=RelationType.USES_MATERIAL,
            object_id="experiment:batch-a",
            confidence=0.88,
        )
        assert rel.predicate == RelationType.USES_MATERIAL

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            ExtractedRelation(
                relation_id="rel:001",
                subject_id="material:lfp",
                # predicate missing
                object_id="experiment:batch-a",
                confidence=0.5,
            )

    def test_confidence_boundary_values(self):
        rel_zero = ExtractedRelation(
            relation_id="r1",
            subject_id="a",
            predicate=RelationType.AFFECTS,
            object_id="b",
            confidence=0.0,
        )
        assert rel_zero.confidence == 0.0

        rel_one = ExtractedRelation(
            relation_id="r2",
            subject_id="a",
            predicate=RelationType.AFFECTS,
            object_id="b",
            confidence=1.0,
        )
        assert rel_one.confidence == 1.0


# --- ClaimCandidate ---


class TestClaimCandidate:
    def test_valid(self):
        claim = ClaimCandidate(
            claim_id="claim:lfp-cap-001",
            text="LFP achieves 170 mAh/g at C/10.",
            claim_type="performance",
            supporting_entities=["material:lfp"],
            source_chunks=["papers/lfp-001:c3"],
            confidence=0.92,
        )
        assert claim.claim_type == "performance"

    def test_empty_text_rejected(self):
        with pytest.raises(ValidationError):
            ClaimCandidate(
                claim_id="claim:001",
                text="",
                claim_type="performance",
                confidence=0.5,
            )

    def test_serialization(self):
        claim = ClaimCandidate(
            claim_id="claim:001",
            text="Some claim.",
            claim_type="mechanism",
            confidence=0.7,
        )
        d = claim.model_dump()
        assert d["claim_id"] == "claim:001"
        assert d["supporting_entities"] == []


# --- WikiPageDraft ---


class TestWikiPageDraft:
    def test_valid(self):
        draft = WikiPageDraft(
            entity_id="material:lfp",
            title="Lithium Iron Phosphate (LFP)",
            sections={"evidence": "| Source | Claim |", "summary": "LFP overview."},
            auto_sections=["evidence"],
            human_sections=["summary"],
        )
        assert "evidence" in draft.sections

    def test_empty_entity_id_rejected(self):
        with pytest.raises(ValidationError):
            WikiPageDraft(entity_id="", title="Title")

    def test_defaults(self):
        draft = WikiPageDraft(entity_id="material:nmc", title="NMC")
        assert draft.sections == {}
        assert draft.auto_sections == []
        assert draft.human_sections == []


# --- GraphPatch ---


class TestGraphPatch:
    def test_valid(self):
        patch = GraphPatch(
            add_nodes=[{"id": "material:lfp", "type": "Material"}],
            add_edges=[{"source": "material:lfp", "target": "experiment:001", "type": "USES_MATERIAL"}],
            remove_nodes=["material:old"],
            remove_edges=[{"source": "a", "target": "b"}],
        )
        assert len(patch.add_nodes) == 1
        assert len(patch.remove_nodes) == 1

    def test_defaults_empty(self):
        patch = GraphPatch()
        assert patch.add_nodes == []
        assert patch.add_edges == []
        assert patch.remove_nodes == []
        assert patch.remove_edges == []

    def test_serialization(self):
        patch = GraphPatch(add_nodes=[{"id": "x"}])
        d = patch.model_dump()
        assert d["add_nodes"] == [{"id": "x"}]


# --- QueryCitation ---


class TestQueryCitation:
    def test_valid(self):
        cite = QueryCitation(
            source_type="paper",
            source_id="papers/lfp-001",
            text="LFP shows 170 mAh/g",
            relevance_score=0.95,
            provenance_path="raw/papers/lfp-001.md §3.2",
        )
        assert cite.relevance_score == 0.95

    def test_relevance_out_of_range(self):
        with pytest.raises(ValidationError):
            QueryCitation(
                source_type="paper",
                source_id="papers/lfp-001",
                text="text",
                relevance_score=1.1,
                provenance_path="raw/x.md",
            )


# --- QueryResultBundle ---


class TestQueryResultBundle:
    def test_valid(self):
        citation = QueryCitation(
            source_type="paper",
            source_id="papers/lfp-001",
            text="LFP capacity",
            relevance_score=0.9,
            provenance_path="raw/papers/lfp-001.md",
        )
        bundle = QueryResultBundle(
            answer="LFP capacity fades due to SEI growth.",
            citations=[citation],
            routing_mode="wiki",
            processing_time_ms=142.5,
        )
        assert len(bundle.citations) == 1
        assert bundle.routing_mode == "wiki"

    def test_negative_processing_time_rejected(self):
        with pytest.raises(ValidationError):
            QueryResultBundle(
                answer="answer",
                citations=[],
                routing_mode="hybrid",
                processing_time_ms=-1.0,
            )

    def test_empty_answer_rejected(self):
        with pytest.raises(ValidationError):
            QueryResultBundle(
                answer="",
                citations=[],
                routing_mode="vector",
                processing_time_ms=100.0,
            )

    def test_serialization_roundtrip(self):
        citation = QueryCitation(
            source_type="wiki",
            source_id="materials/lfp",
            text="Overview",
            relevance_score=0.8,
            provenance_path="wiki/materials/lfp.md",
        )
        bundle = QueryResultBundle(
            answer="Answer text.",
            citations=[citation],
            routing_mode="hybrid",
            processing_time_ms=200.0,
        )
        json_str = bundle.model_dump_json()
        restored = QueryResultBundle.model_validate_json(json_str)
        assert restored.answer == bundle.answer
        assert len(restored.citations) == 1
        assert restored.citations[0].source_id == "materials/lfp"


# --- Stage Output Validation ---


class TestExtractJson:
    def test_raw_object(self):
        assert _extract_json('{"key": "value"}') == '{"key": "value"}'

    def test_raw_array(self):
        assert _extract_json("[1, 2, 3]") == "[1, 2, 3]"

    def test_markdown_fenced(self):
        text = '```json\n{"key": "value"}\n```'
        assert _extract_json(text) == '{"key": "value"}'

    def test_plain_text_returns_none(self):
        assert _extract_json("This is not JSON") is None

    def test_empty_string_returns_none(self):
        assert _extract_json("") is None

    def test_whitespace_only_returns_none(self):
        assert _extract_json("   ") is None


class TestMatchesAnyModel:
    def test_matches_source_document(self):
        data = {
            "doc_id": "papers/lfp-001",
            "source_path": "raw/papers/lfp-001.md",
            "doc_type": "paper",
            "content_hash": "sha256:abc123",
            "ingested_at": "2026-04-24T12:00:00Z",
        }
        assert _matches_any_model(data, [SourceDocument]) is True

    def test_rejects_invalid_data(self):
        data = {"not": "a valid model"}
        assert _matches_any_model(data, [SourceDocument]) is False

    def test_matches_any_of_multiple(self):
        entity_data = {
            "entity_id": "material:lfp",
            "name": "LFP",
            "entity_type": "Material",
            "confidence": 0.9,
        }
        assert _matches_any_model(entity_data, [ExtractedEntity, ExtractedRelation]) is True

    def test_no_models_match(self):
        data = {"entity_id": "x", "name": "y"}
        assert _matches_any_model(data, [SourceDocument, ExtractedRelation]) is False


class TestValidateStageOutput:
    def test_empty_output_raises(self):
        with pytest.raises(StageOutputValidationError, match="empty output"):
            PipelineRunner._validate_stage_output(ProcessingStage.INGESTED, "")

    def test_whitespace_only_raises(self):
        with pytest.raises(StageOutputValidationError, match="empty output"):
            PipelineRunner._validate_stage_output(ProcessingStage.INGESTED, "   ")

    def test_non_json_output_raises(self):
        with pytest.raises(StageOutputValidationError, match="does not contain valid JSON"):
            PipelineRunner._validate_stage_output(
                ProcessingStage.INGESTED, "I processed the document successfully."
            )

    def test_invalid_json_raises(self):
        with pytest.raises(StageOutputValidationError, match="Invalid JSON"):
            PipelineRunner._validate_stage_output(
                ProcessingStage.INGESTED, "{bad json"
            )

    def test_valid_ingestion_output(self):
        data = {
            "doc_id": "papers/lfp-001",
            "source_path": "raw/papers/lfp-001.md",
            "doc_type": "paper",
            "content_hash": "sha256:abc",
            "ingested_at": "2026-04-24T12:00:00Z",
        }
        # Should not raise
        PipelineRunner._validate_stage_output(
            ProcessingStage.INGESTED, json.dumps(data)
        )

    def test_invalid_ingestion_output_missing_fields(self):
        data = {"doc_id": "papers/lfp-001"}  # Missing required fields
        with pytest.raises(StageOutputValidationError, match="does not conform"):
            PipelineRunner._validate_stage_output(
                ProcessingStage.INGESTED, json.dumps(data)
            )

    def test_valid_extraction_output_entity(self):
        data = {
            "entity_id": "material:lfp",
            "name": "LFP",
            "entity_type": "Material",
            "confidence": 0.9,
        }
        PipelineRunner._validate_stage_output(
            ProcessingStage.EXTRACTED, json.dumps(data)
        )

    def test_valid_extraction_output_relation(self):
        data = {
            "relation_id": "rel:001",
            "subject_id": "material:lfp",
            "predicate": "USES_MATERIAL",
            "object_id": "experiment:batch-a",
            "confidence": 0.88,
        }
        PipelineRunner._validate_stage_output(
            ProcessingStage.EXTRACTED, json.dumps(data)
        )

    def test_valid_extraction_output_list(self):
        data = [
            {
                "entity_id": "material:lfp",
                "name": "LFP",
                "entity_type": "Material",
                "confidence": 0.9,
            },
            {
                "relation_id": "rel:001",
                "subject_id": "material:lfp",
                "predicate": "USES_MATERIAL",
                "object_id": "experiment:batch-a",
                "confidence": 0.88,
            },
        ]
        PipelineRunner._validate_stage_output(
            ProcessingStage.EXTRACTED, json.dumps(data)
        )

    def test_invalid_list_item_raises(self):
        data = [
            {
                "entity_id": "material:lfp",
                "name": "LFP",
                "entity_type": "Material",
                "confidence": 0.9,
            },
            {"bad": "item"},  # Does not match any contract
        ]
        with pytest.raises(StageOutputValidationError, match="Item 1 does not conform"):
            PipelineRunner._validate_stage_output(
                ProcessingStage.EXTRACTED, json.dumps(data)
            )

    def test_valid_wiki_output(self):
        data = {"entity_id": "material:lfp", "title": "LFP"}
        PipelineRunner._validate_stage_output(
            ProcessingStage.WIKI_COMPILED, json.dumps(data)
        )

    def test_valid_graph_output(self):
        data = {"add_nodes": [{"id": "material:lfp"}], "add_edges": []}
        PipelineRunner._validate_stage_output(
            ProcessingStage.GRAPH_UPDATED, json.dumps(data)
        )

    def test_markdown_fenced_json_accepted(self):
        data = {"entity_id": "material:lfp", "title": "LFP"}
        fenced = f"```json\n{json.dumps(data)}\n```"
        PipelineRunner._validate_stage_output(
            ProcessingStage.WIKI_COMPILED, fenced
        )

    def test_error_includes_stage_name(self):
        with pytest.raises(StageOutputValidationError) as exc_info:
            PipelineRunner._validate_stage_output(ProcessingStage.INGESTED, "")
        assert exc_info.value.stage == ProcessingStage.INGESTED
        assert "ingested" in str(exc_info.value)
