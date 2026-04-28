"""Tests for WikiMaterializer — deterministic wiki projection from claims/evidence."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from llm_rag.evidence.models import (
    DocumentType,
    EvidenceChunk,
    EvidenceDocument,
    EvidenceStore,
    ProvenanceSpan,
)
from llm_rag.knowledge.models import (
    ClaimCollection,
    ClaimStatus,
    EntityClaim,
    RelationClaim,
)
from llm_rag.schemas.entities import EntityType, RelationType
from llm_rag.wiki.materializer import WikiMaterializer

_FIXED_DT = datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC)

_MATERIAL_TEMPLATE = """\
---
entity_type: material
entity_id: "{{ entity_id }}"
canonical_name: "{{ canonical_name }}"
created: "{{ created }}"
---

# {{ canonical_name }}

## Summary
<!-- human-start: summary -->

<!-- human-end: summary -->

## Properties
<!-- auto-start: properties -->
<!-- auto-end: properties -->

## Linked Entities
<!-- auto-start: linked-entities -->
<!-- auto-end: linked-entities -->

## Evidence
<!-- auto-start: evidence -->
<!-- auto-end: evidence -->

## Contradictions
<!-- auto-start: contradictions -->
<!-- auto-end: contradictions -->

## Open Questions
<!-- human-start: open-questions -->

<!-- human-end: open-questions -->

## Provenance
<!-- auto-start: provenance -->
<!-- auto-end: provenance -->

## Last Updated
<!-- auto-start: last-updated -->
<!-- auto-end: last-updated -->
"""


def _make_evidence_store() -> EvidenceStore:
    doc = EvidenceDocument(
        doc_id="papers/lfp-001",
        source_path="raw/papers/lfp-001.md",
        doc_type=DocumentType.PAPER,
        content_hash="sha256:aaa",
        title="LFP Capacity Study",
        ingested_at=_FIXED_DT,
    )
    chunk = EvidenceChunk(
        chunk_id="papers/lfp-001:chunk-000",
        document_id="papers/lfp-001",
        text="LFP shows 170 mAh/g capacity.",
        content_hash=EvidenceChunk.hash_text("LFP shows 170 mAh/g capacity."),
        span=ProvenanceSpan(start_byte=0, end_byte=30),
        chunk_index=0,
        token_estimate=7,
    )
    return EvidenceStore(document=doc, chunks=[chunk])


def _make_claims() -> ClaimCollection:
    return ClaimCollection(
        source_doc_id="papers/lfp-001",
        entity_claims=[
            EntityClaim(
                claim_id="claim:lfp-cap-001",
                statement="LFP has 170 mAh/g theoretical capacity",
                confidence=0.92,
                source_doc_id="papers/lfp-001",
                evidence_chunk_ids=["papers/lfp-001:chunk-000"],
                entity_id="material:lfp",
                entity_type=EntityType.MATERIAL,
                property_name="capacity_mah_g",
                property_value="170",
                extracted_at=_FIXED_DT,
            ),
        ],
        relation_claims=[
            RelationClaim(
                claim_id="claim:lfp-uses-001",
                statement="LFP uses olivine crystal structure",
                confidence=0.85,
                source_doc_id="papers/lfp-001",
                evidence_chunk_ids=["papers/lfp-001:chunk-000"],
                source_entity_id="material:lfp",
                target_entity_id="property:olivine",
                relation_type=RelationType.PRODUCES_PROPERTY,
                extracted_at=_FIXED_DT,
            ),
        ],
        extracted_at=_FIXED_DT,
    )


@pytest.fixture()
def materializer(tmp_path: Path) -> WikiMaterializer:
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "material.md").write_text(_MATERIAL_TEMPLATE)
    (template_dir / "_fallback.md").write_text(_MATERIAL_TEMPLATE)
    return WikiMaterializer(wiki_dir=wiki_dir, template_dir=template_dir)


class TestBuildWikiPage:
    def test_creates_page_from_template(
        self, materializer: WikiMaterializer
    ) -> None:
        result = materializer.build_wiki_page(
            entity_id="material:lfp",
            entity_type="material",
            canonical_name="LFP",
            claims=_make_claims(),
            evidence=_make_evidence_store(),
            relative_path="materials/lfp.md",
        )
        assert "# LFP" in result
        assert 'entity_id: "material:lfp"' in result

    def test_auto_sections_populated(
        self, materializer: WikiMaterializer
    ) -> None:
        result = materializer.build_wiki_page(
            entity_id="material:lfp",
            entity_type="material",
            canonical_name="LFP",
            claims=_make_claims(),
            evidence=_make_evidence_store(),
            relative_path="materials/lfp.md",
        )
        # Properties section has the entity claim
        assert "capacity_mah_g" in result
        assert "170" in result
        # Linked entities section has the relation
        assert "property:olivine" in result
        assert "PRODUCES_PROPERTY" in result
        # Evidence section has the claim statement
        assert "LFP has 170 mAh/g theoretical capacity" in result

    def test_human_sections_preserved(
        self, materializer: WikiMaterializer
    ) -> None:
        """Human sections from existing pages survive materialization."""
        page_path = materializer.wiki_dir / "materials" / "lfp.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        content = _MATERIAL_TEMPLATE.replace(
            "{{ entity_id }}", "material:lfp"
        ).replace("{{ canonical_name }}", "LFP").replace(
            "{{ created }}", "2026-04-20"
        )
        # Insert human content
        content = content.replace(
            "<!-- human-start: summary -->\n\n<!-- human-end: summary -->",
            "<!-- human-start: summary -->\nMy custom summary.\n<!-- human-end: summary -->",
        )
        content = content.replace(
            "<!-- human-start: open-questions -->\n\n<!-- human-end: open-questions -->",
            "<!-- human-start: open-questions -->\n- What about 5C rate?\n<!-- human-end: open-questions -->",
        )
        page_path.write_text(content)

        result = materializer.build_wiki_page(
            entity_id="material:lfp",
            entity_type="material",
            canonical_name="LFP",
            claims=_make_claims(),
            evidence=_make_evidence_store(),
            relative_path="materials/lfp.md",
        )
        assert "My custom summary." in result
        assert "What about 5C rate?" in result
        # Auto sections also populated
        assert "capacity_mah_g" in result


class TestDeterministicOutput:
    def test_same_input_same_output(
        self, materializer: WikiMaterializer, tmp_path: Path
    ) -> None:
        """Running materialization twice with same input produces same auto-section content."""
        claims = _make_claims()
        evidence = _make_evidence_store()

        result1 = materializer.build_wiki_page(
            entity_id="material:lfp",
            entity_type="material",
            canonical_name="LFP",
            claims=claims,
            evidence=evidence,
            relative_path="materials/lfp.md",
        )

        # Run again — same inputs
        result2 = materializer.build_wiki_page(
            entity_id="material:lfp",
            entity_type="material",
            canonical_name="LFP",
            claims=claims,
            evidence=evidence,
            relative_path="materials/lfp.md",
        )

        # Extract auto sections for comparison (last-updated will differ by timestamp)
        # Compare all sections except last-updated
        for section in ["properties", "linked-entities", "evidence", "contradictions", "provenance"]:
            s1 = _extract_auto_section(result1, section)
            s2 = _extract_auto_section(result2, section)
            assert s1 == s2, f"Section {section!r} differs between runs"

    def test_sorted_claims_ensure_determinism(
        self, materializer: WikiMaterializer
    ) -> None:
        """Claims are sorted by claim_id so ordering is stable."""
        claims = ClaimCollection(
            source_doc_id="papers/lfp-001",
            entity_claims=[
                EntityClaim(
                    claim_id="claim:zzz",
                    statement="Z claim",
                    confidence=0.8,
                    source_doc_id="papers/lfp-001",
                    evidence_chunk_ids=["papers/lfp-001:chunk-000"],
                    entity_id="material:lfp",
                    entity_type=EntityType.MATERIAL,
                    property_name="z_prop",
                    property_value="z_val",
                    extracted_at=_FIXED_DT,
                ),
                EntityClaim(
                    claim_id="claim:aaa",
                    statement="A claim",
                    confidence=0.9,
                    source_doc_id="papers/lfp-001",
                    evidence_chunk_ids=["papers/lfp-001:chunk-000"],
                    entity_id="material:lfp",
                    entity_type=EntityType.MATERIAL,
                    property_name="a_prop",
                    property_value="a_val",
                    extracted_at=_FIXED_DT,
                ),
            ],
            extracted_at=_FIXED_DT,
        )
        result = materializer.build_wiki_page(
            entity_id="material:lfp",
            entity_type="material",
            canonical_name="LFP",
            claims=claims,
            evidence=_make_evidence_store(),
            relative_path="materials/lfp-sort.md",
        )
        props = _extract_auto_section(result, "properties")
        # a_prop should appear before z_prop (sorted by property_name)
        assert props.index("a_prop") < props.index("z_prop")


class TestEdgeCases:
    def test_empty_claims(self, materializer: WikiMaterializer) -> None:
        """Empty claim collection produces placeholder text in sections."""
        claims = ClaimCollection(
            source_doc_id="papers/lfp-001",
            extracted_at=_FIXED_DT,
        )
        result = materializer.build_wiki_page(
            entity_id="material:lfp",
            entity_type="material",
            canonical_name="LFP",
            claims=claims,
            evidence=_make_evidence_store(),
            relative_path="materials/lfp-empty.md",
        )
        assert "_No properties extracted._" in result
        assert "_No linked entities._" in result
        assert "_No contradictions detected._" in result

    def test_disputed_claims_in_contradictions(
        self, materializer: WikiMaterializer
    ) -> None:
        """Disputed claims appear in the contradictions section."""
        claims = ClaimCollection(
            source_doc_id="papers/lfp-001",
            entity_claims=[
                EntityClaim(
                    claim_id="claim:disputed-001",
                    statement="LFP capacity is only 150 mAh/g",
                    confidence=0.6,
                    source_doc_id="papers/lfp-001",
                    evidence_chunk_ids=["papers/lfp-001:chunk-000"],
                    entity_id="material:lfp",
                    entity_type=EntityType.MATERIAL,
                    property_name="capacity_mah_g",
                    property_value="150",
                    status=ClaimStatus.DISPUTED,
                    extracted_at=_FIXED_DT,
                ),
            ],
            extracted_at=_FIXED_DT,
        )
        result = materializer.build_wiki_page(
            entity_id="material:lfp",
            entity_type="material",
            canonical_name="LFP",
            claims=claims,
            evidence=_make_evidence_store(),
            relative_path="materials/lfp-disputed.md",
        )
        contradictions = _extract_auto_section(result, "contradictions")
        assert "LFP capacity is only 150 mAh/g" in contradictions
        assert "disputed" in contradictions

    def test_fallback_template(self, materializer: WikiMaterializer) -> None:
        """Unknown entity type falls back to _fallback.md template."""
        result = materializer.build_wiki_page(
            entity_id="custom:thing",
            entity_type="noveltype",
            canonical_name="Novel Thing",
            claims=ClaimCollection(
                source_doc_id="papers/lfp-001", extracted_at=_FIXED_DT
            ),
            evidence=_make_evidence_store(),
            relative_path="custom/thing.md",
        )
        assert "# Novel Thing" in result


class TestRoundtrip:
    def test_materialize_then_rematerialize_preserves_human(
        self, materializer: WikiMaterializer
    ) -> None:
        """Materialize, add human content, re-materialize — human content survives."""
        claims = _make_claims()
        evidence = _make_evidence_store()

        # First materialization
        materializer.build_wiki_page(
            entity_id="material:lfp",
            entity_type="material",
            canonical_name="LFP",
            claims=claims,
            evidence=evidence,
            relative_path="materials/lfp-rt.md",
        )

        # Simulate human editing the summary section
        page_path = materializer.wiki_dir / "materials" / "lfp-rt.md"
        content = page_path.read_text()
        content = content.replace(
            "<!-- human-start: summary -->\n\n<!-- human-end: summary -->",
            "<!-- human-start: summary -->\nHuman wrote this.\n<!-- human-end: summary -->",
        )
        page_path.write_text(content)

        # Re-materialize with updated claims
        result = materializer.build_wiki_page(
            entity_id="material:lfp",
            entity_type="material",
            canonical_name="LFP",
            claims=claims,
            evidence=evidence,
            relative_path="materials/lfp-rt.md",
        )

        assert "Human wrote this." in result
        # Auto sections still present
        assert "capacity_mah_g" in result


def _extract_auto_section(page_text: str, section_name: str) -> str:
    """Extract content between auto-start and auto-end tags."""
    import re

    match = re.search(
        rf"<!-- auto-start: {re.escape(section_name)} -->(.*?)<!-- auto-end: {re.escape(section_name)} -->",
        page_text,
        re.DOTALL,
    )
    return match.group(1).strip() if match else ""
