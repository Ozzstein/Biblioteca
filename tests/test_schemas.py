from datetime import UTC, datetime

import pytest

from llm_rag.schemas.entities import (
    Cell,
    Claim,
    Entity,
    EntityType,
    ExtractionResult,
    InternalReport,
    Material,
    Meeting,
    Relation,
    RelationType,
    Sop,
)
from llm_rag.schemas.provenance import (
    DocType,
    DocumentManifest,
    ExtractionMethod,
    ProcessingStage,
    ProvenanceRecord,
)
from llm_rag.schemas.wiki import WikiPage, WikiSection


def make_provenance() -> ProvenanceRecord:
    return ProvenanceRecord(
        source_doc_id="papers/test-001",
        source_path="raw/papers/test-001.md",
        section="§3.2",
        timestamp=datetime(2026, 4, 18, tzinfo=UTC),
        confidence=0.92,
        extraction_method=ExtractionMethod.CLAUDE_HAIKU,
        extractor_model="claude-haiku-4-5-20251001",
    )


def test_provenance_record_valid():
    p = make_provenance()
    assert p.confidence == 0.92
    assert p.extraction_method == ExtractionMethod.CLAUDE_HAIKU
    assert p.section == "§3.2"


def test_provenance_confidence_too_high():
    with pytest.raises(Exception):
        ProvenanceRecord(
            source_doc_id="x",
            source_path="x",
            timestamp=datetime.now(UTC),
            confidence=1.5,
            extraction_method=ExtractionMethod.MANUAL,
        )


def test_provenance_confidence_negative():
    with pytest.raises(Exception):
        ProvenanceRecord(
            source_doc_id="x",
            source_path="x",
            timestamp=datetime.now(UTC),
            confidence=-0.1,
            extraction_method=ExtractionMethod.MANUAL,
        )


def test_provenance_optional_fields_default_none():
    p = ProvenanceRecord(
        source_doc_id="papers/x",
        source_path="raw/x",
        timestamp=datetime.now(UTC),
        confidence=0.8,
        extraction_method=ExtractionMethod.RULE_BASED,
    )
    assert p.section is None
    assert p.extractor_model is None


def test_document_manifest_defaults():
    m = DocumentManifest(
        doc_id="papers/test-001",
        source_path="raw/papers/test-001.md",
        content_hash="sha256:abc123",
        doc_type="paper",
        source_connector="arxiv",
        fetched_at=datetime.now(UTC),
        last_processed=datetime.now(UTC),
    )
    assert m.stages_completed == []
    assert m.authors == []
    assert m.doi is None
    assert m.error is None
    assert m.doc_type == DocType.PAPER


def test_document_manifest_with_stages():
    m = DocumentManifest(
        doc_id="papers/test-001",
        source_path="raw/papers/test-001.md",
        content_hash="sha256:abc123",
        doc_type="paper",
        source_connector="manual",
        fetched_at=datetime.now(UTC),
        last_processed=datetime.now(UTC),
        stages_completed=[ProcessingStage.INGESTED, ProcessingStage.EXTRACTED],
    )
    assert ProcessingStage.INGESTED in m.stages_completed
    assert ProcessingStage.WIKI_COMPILED not in m.stages_completed


def test_sop_entity_defaults():
    sop = Sop(
        entity_id="sop:SOP-001:v1",
        canonical_name="SOP-001 v1",
        sop_id="SOP-001",
        version="v1",
    )
    assert sop.entity_type == EntityType.SOP
    assert sop.status == "unknown"
    assert sop.deprecated is False


def test_meeting_entity_fields():
    meeting = Meeting(
        entity_id="meeting:2026-04-27-ops",
        canonical_name="Ops Sync 2026-04-27",
        attendees=["alice", "bob"],
        decisions=["Ship update"],
        action_items=["Update SOP-001"],
    )
    assert meeting.entity_type == EntityType.MEETING
    assert "alice" in meeting.attendees


def test_internal_report_metrics():
    report = InternalReport(
        entity_id="internal-report:RPT-022",
        canonical_name="RPT-022",
        report_id="RPT-022",
        key_metrics={"yield": "97.5%"},
    )
    assert report.entity_type == EntityType.INTERNAL_REPORT
    assert report.key_metrics["yield"] == "97.5%"


def test_entity_base():
    e = Entity(
        entity_id="material:lfp",
        entity_type=EntityType.MATERIAL,
        canonical_name="LFP",
    )
    assert e.aliases == []
    assert e.provenance == []
    assert e.wiki_page is None


def test_material_entity_type():
    m = Material(
        entity_id="material:lfp",
        canonical_name="LFP",
        aliases=["LiFePO4", "lithium iron phosphate"],
        formula="LiFePO4",
        material_class="cathode",
    )
    assert m.entity_type == EntityType.MATERIAL
    assert m.formula == "LiFePO4"
    assert m.crystal_structure is None


def test_cell_entity():
    c = Cell(
        entity_id="cell:pouch-lfp-001",
        canonical_name="LFP Pouch Cell 2Ah",
        chemistry="LFP/graphite",
        form_factor="pouch",
        capacity_mah=2000.0,
    )
    assert c.entity_type == EntityType.CELL
    assert c.capacity_mah == 2000.0


def test_claim_entity():
    c = Claim(
        entity_id="claim:lfp-capacity-001",
        canonical_name="LFP theoretical capacity",
        statement="LFP has a theoretical specific capacity of 170 mAh/g",
        supported_by=["papers/sample-001"],
        contradicted_by=[],
    )
    assert c.entity_type == EntityType.CLAIM
    assert "papers/sample-001" in c.supported_by


def test_relation():
    r = Relation(
        relation_id="rel-001",
        relation_type=RelationType.USES_MATERIAL,
        source_entity_id="experiment:001",
        target_entity_id="material:lfp",
    )
    assert r.weight == 1.0
    assert r.provenance == []


def test_extraction_result_empty():
    result = ExtractionResult(
        doc_id="papers/test-001",
        extraction_model="claude-haiku-4-5-20251001",
        extracted_at=datetime.now(UTC),
    )
    assert result.entities == []
    assert result.relations == []
    assert result.chunks_processed == 0


def test_extraction_result_with_entities():
    m = Material(
        entity_id="material:lfp",
        canonical_name="LFP",
        formula="LiFePO4",
    )
    result = ExtractionResult(
        doc_id="papers/test-001",
        entities=[m],
        chunks_processed=5,
        extraction_model="claude-haiku-4-5-20251001",
        extracted_at=datetime.now(UTC),
    )
    assert len(result.entities) == 1
    assert result.chunks_processed == 5


def test_wiki_section_auto():
    s = WikiSection(name="evidence", managed_by="auto", content="| Source | Claim |")
    assert s.managed_by == "auto"
    assert "Source" in s.content


def test_wiki_section_human():
    s = WikiSection(name="summary", managed_by="human", content="LFP is stable.")
    assert s.managed_by == "human"


def test_wiki_section_defaults_empty_content():
    s = WikiSection(name="contradictions", managed_by="auto")
    assert s.content == ""


def test_wiki_page_defaults():
    page = WikiPage(
        page_type="material",
        entity_id="material:lfp",
        canonical_name="LFP",
        path="wiki/materials/lfp.md",
    )
    assert page.sections == {}
    assert page.last_auto_updated is None
    assert page.last_human_edited is None


def test_wiki_page_with_sections():
    page = WikiPage(
        page_type="material",
        entity_id="material:lfp",
        canonical_name="LFP",
        path="wiki/materials/lfp.md",
        sections={
            "evidence": WikiSection(name="evidence", managed_by="auto", content="..."),
            "summary": WikiSection(name="summary", managed_by="human", content="..."),
        },
    )
    assert "evidence" in page.sections
    assert page.sections["evidence"].managed_by == "auto"
    assert page.sections["summary"].managed_by == "human"
