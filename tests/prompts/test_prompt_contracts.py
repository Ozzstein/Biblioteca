"""Golden tests for prompt-driven pipeline stage output parsing.

Each test loads a fixture JSON file representing the expected output shape
of a pipeline stage, then validates it through the actual Pydantic models.
Edge-case tests verify that malformed, missing-field, and extra-field
inputs are handled correctly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from llm_rag.pipeline.contracts import (
    ExtractedEntity,
    ExtractedRelation,
    GraphPatch,
    SourceDocument,
    WikiPageDraft,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load(name: str) -> dict | list:
    return json.loads((FIXTURES / name).read_text())


# ---------------------------------------------------------------------------
# 1. Ingestion Agent — SourceDocument
# ---------------------------------------------------------------------------

class TestIngestionContract:
    def test_valid_fixture_parses(self):
        data = _load("ingestion_valid.json")
        doc = SourceDocument(**data)
        assert doc.doc_id == "papers/sample-lfp-001"
        assert doc.doc_type == "paper"
        assert doc.content_hash.startswith("sha256:")

    def test_all_required_fields_present(self):
        data = _load("ingestion_valid.json")
        for field in ("doc_id", "source_path", "doc_type", "content_hash", "ingested_at"):
            assert field in data

    def test_missing_doc_id_fails(self):
        data = _load("ingestion_valid.json")
        del data["doc_id"]
        with pytest.raises(ValidationError):
            SourceDocument(**data)

    def test_empty_doc_id_fails(self):
        data = _load("ingestion_valid.json")
        data["doc_id"] = ""
        with pytest.raises(ValidationError):
            SourceDocument(**data)

    def test_missing_content_hash_fails(self):
        data = _load("ingestion_valid.json")
        del data["content_hash"]
        with pytest.raises(ValidationError):
            SourceDocument(**data)

    def test_invalid_datetime_fails(self):
        data = _load("ingestion_valid.json")
        data["ingested_at"] = "not-a-date"
        with pytest.raises(ValidationError):
            SourceDocument(**data)

    def test_extra_fields_ignored(self):
        data = _load("ingestion_valid.json")
        data["unexpected_field"] = "surprise"
        doc = SourceDocument(**data)
        assert doc.doc_id == "papers/sample-lfp-001"


# ---------------------------------------------------------------------------
# 2. Extraction Agent — ExtractedEntity + ExtractedRelation
# ---------------------------------------------------------------------------

class TestExtractionContract:
    def test_valid_entities_parse(self):
        data = _load("extraction_valid.json")
        entities = [ExtractedEntity(**e) for e in data["entities"]]
        assert len(entities) == 3
        assert entities[0].entity_id == "material:lfp"
        assert entities[0].entity_type.value == "Material"

    def test_valid_relations_parse(self):
        data = _load("extraction_valid.json")
        relations = [ExtractedRelation(**r) for r in data["relations"]]
        assert len(relations) == 2
        assert relations[0].predicate.value == "CAUSES"

    def test_confidence_bounds(self):
        data = _load("extraction_valid.json")
        for e in data["entities"]:
            entity = ExtractedEntity(**e)
            assert 0.0 <= entity.confidence <= 1.0

    def test_confidence_above_1_fails(self):
        data = _load("extraction_valid.json")
        data["entities"][0]["confidence"] = 1.5
        with pytest.raises(ValidationError):
            ExtractedEntity(**data["entities"][0])

    def test_confidence_below_0_fails(self):
        data = _load("extraction_valid.json")
        data["entities"][0]["confidence"] = -0.1
        with pytest.raises(ValidationError):
            ExtractedEntity(**data["entities"][0])

    def test_invalid_entity_type_fails(self):
        data = _load("extraction_valid.json")
        data["entities"][0]["entity_type"] = "InvalidType"
        with pytest.raises(ValidationError):
            ExtractedEntity(**data["entities"][0])

    def test_invalid_relation_type_fails(self):
        data = _load("extraction_valid.json")
        data["relations"][0]["predicate"] = "INVALID_RELATION"
        with pytest.raises(ValidationError):
            ExtractedRelation(**data["relations"][0])

    def test_missing_entity_name_fails(self):
        data = _load("extraction_valid.json")
        del data["entities"][0]["name"]
        with pytest.raises(ValidationError):
            ExtractedEntity(**data["entities"][0])

    def test_missing_subject_id_fails(self):
        data = _load("extraction_valid.json")
        del data["relations"][0]["subject_id"]
        with pytest.raises(ValidationError):
            ExtractedRelation(**data["relations"][0])

    def test_empty_aliases_allowed(self):
        data = _load("extraction_valid.json")
        data["entities"][0]["aliases"] = []
        entity = ExtractedEntity(**data["entities"][0])
        assert entity.aliases == []

    def test_extra_fields_on_entity_ignored(self):
        data = _load("extraction_valid.json")
        data["entities"][0]["extra_key"] = "extra_value"
        entity = ExtractedEntity(**data["entities"][0])
        assert entity.entity_id == "material:lfp"


# ---------------------------------------------------------------------------
# 3. Normalization Agent — normalized ExtractedEntity list
# ---------------------------------------------------------------------------

class TestNormalizationContract:
    def test_valid_fixture_parses(self):
        data = _load("normalization_valid.json")
        entities = [ExtractedEntity(**e) for e in data]
        assert len(entities) == 3

    def test_aliases_expanded(self):
        data = _load("normalization_valid.json")
        lfp = ExtractedEntity(**data[0])
        assert "lithium-iron-phosphate" in lfp.aliases
        assert "LFP" in lfp.aliases

    def test_canonical_names_preserved(self):
        data = _load("normalization_valid.json")
        entities = [ExtractedEntity(**e) for e in data]
        names = {e.name for e in entities}
        assert "Lithium Iron Phosphate" in names
        assert "Solid Electrolyte Interphase" in names

    def test_empty_list_valid(self):
        entities = [ExtractedEntity(**e) for e in []]
        assert entities == []

    def test_duplicate_alias_allowed(self):
        data = _load("normalization_valid.json")
        data[0]["aliases"] = ["LFP", "LFP"]
        entity = ExtractedEntity(**data[0])
        assert entity.aliases == ["LFP", "LFP"]

    def test_missing_entity_type_fails(self):
        data = _load("normalization_valid.json")
        del data[0]["entity_type"]
        with pytest.raises(ValidationError):
            ExtractedEntity(**data[0])


# ---------------------------------------------------------------------------
# 4. Wiki Compiler Agent — WikiPageDraft
# ---------------------------------------------------------------------------

class TestWikiCompilerContract:
    def test_valid_fixture_parses(self):
        data = _load("wiki_compiler_valid.json")
        draft = WikiPageDraft(**data)
        assert draft.entity_id == "material:lfp"
        assert draft.title == "Lithium Iron Phosphate (LFP)"

    def test_sections_dict_populated(self):
        data = _load("wiki_compiler_valid.json")
        draft = WikiPageDraft(**data)
        assert "evidence" in draft.sections
        assert "linked-entities" in draft.sections
        assert "properties" in draft.sections

    def test_auto_and_human_sections_listed(self):
        data = _load("wiki_compiler_valid.json")
        draft = WikiPageDraft(**data)
        assert "evidence" in draft.auto_sections
        assert "summary" in draft.human_sections

    def test_missing_entity_id_fails(self):
        data = _load("wiki_compiler_valid.json")
        del data["entity_id"]
        with pytest.raises(ValidationError):
            WikiPageDraft(**data)

    def test_empty_title_fails(self):
        data = _load("wiki_compiler_valid.json")
        data["title"] = ""
        with pytest.raises(ValidationError):
            WikiPageDraft(**data)

    def test_empty_sections_allowed(self):
        data = _load("wiki_compiler_valid.json")
        data["sections"] = {}
        data["auto_sections"] = []
        draft = WikiPageDraft(**data)
        assert draft.sections == {}

    def test_extra_fields_ignored(self):
        data = _load("wiki_compiler_valid.json")
        data["revision"] = 42
        draft = WikiPageDraft(**data)
        assert draft.entity_id == "material:lfp"


# ---------------------------------------------------------------------------
# 5. Graph Curator Agent — GraphPatch
# ---------------------------------------------------------------------------

class TestGraphCuratorContract:
    def test_valid_fixture_parses(self):
        data = _load("graph_curator_valid.json")
        patch = GraphPatch(**data)
        assert len(patch.add_nodes) == 3
        assert len(patch.add_edges) == 2

    def test_node_structure(self):
        data = _load("graph_curator_valid.json")
        patch = GraphPatch(**data)
        node = patch.add_nodes[0]
        assert "id" in node
        assert "entity_type" in node

    def test_edge_structure(self):
        data = _load("graph_curator_valid.json")
        patch = GraphPatch(**data)
        edge = patch.add_edges[0]
        assert "source" in edge
        assert "target" in edge
        assert "relation_type" in edge

    def test_empty_patch_valid(self):
        patch = GraphPatch()
        assert patch.add_nodes == []
        assert patch.add_edges == []
        assert patch.remove_nodes == []
        assert patch.remove_edges == []

    def test_remove_nodes_list(self):
        data = _load("graph_curator_valid.json")
        data["remove_nodes"] = ["material:old-entity"]
        patch = GraphPatch(**data)
        assert patch.remove_nodes == ["material:old-entity"]

    def test_remove_edges_list(self):
        data = _load("graph_curator_valid.json")
        data["remove_edges"] = [{"source": "a", "target": "b"}]
        patch = GraphPatch(**data)
        assert len(patch.remove_edges) == 1

    def test_extra_fields_ignored(self):
        data = _load("graph_curator_valid.json")
        data["metadata"] = {"version": 1}
        patch = GraphPatch(**data)
        assert len(patch.add_nodes) == 3


# ---------------------------------------------------------------------------
# 6. Cross-cutting: malformed JSON edge cases
# ---------------------------------------------------------------------------

class TestMalformedJson:
    def test_completely_empty_object_fails_source_document(self):
        with pytest.raises(ValidationError):
            SourceDocument(**{})

    def test_null_values_for_required_fields_fail(self):
        data = _load("ingestion_valid.json")
        data["doc_id"] = None
        with pytest.raises(ValidationError):
            SourceDocument(**data)

    def test_wrong_type_for_confidence(self):
        data = _load("extraction_valid.json")
        data["entities"][0]["confidence"] = "high"
        with pytest.raises(ValidationError):
            ExtractedEntity(**data["entities"][0])

    def test_wrong_type_for_sections_dict(self):
        data = _load("wiki_compiler_valid.json")
        data["sections"] = "not a dict"
        with pytest.raises(ValidationError):
            WikiPageDraft(**data)

    def test_wrong_type_for_add_nodes(self):
        with pytest.raises(ValidationError):
            GraphPatch(add_nodes="not a list")

    def test_integer_for_string_field_rejected(self):
        """Pydantic rejects int where str is expected (strict string mode)."""
        data = _load("ingestion_valid.json")
        data["doc_id"] = 12345
        with pytest.raises(ValidationError):
            SourceDocument(**data)
