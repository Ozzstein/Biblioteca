"""Wiki page materializer — deterministic projection from claims + evidence.

Generates wiki auto-sections from ClaimCollection and EvidenceStore,
preserving human-editable sections from existing pages.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from llm_rag.evidence.models import EvidenceStore
from llm_rag.knowledge.models import (
    Claim,
    ClaimCollection,
    ClaimStatus,
    EntityClaim,
    RelationClaim,
)
from llm_rag.wiki.writer import create_page, update_auto_sections


class WikiMaterializer:
    """Deterministically generates wiki pages from claims and evidence.

    Auto-sections are rebuilt from the claim/evidence data on every call.
    Human-sections are read from the existing page and preserved verbatim.
    """

    def __init__(
        self,
        wiki_dir: Path,
        template_dir: Path,
    ) -> None:
        self.wiki_dir = wiki_dir
        self.template_dir = template_dir

    def build_wiki_page(
        self,
        entity_id: str,
        entity_type: str,
        canonical_name: str,
        claims: ClaimCollection,
        evidence: EvidenceStore,
        relative_path: str,
    ) -> str:
        """Generate a wiki page from claims + evidence, preserving human sections.

        Returns the full page markdown. Also writes the file to disk.
        """
        page_path = self.wiki_dir / relative_path

        # Ensure page exists (create from template if not)
        if not page_path.exists():
            template = self._load_template(entity_type)
            create_page(
                page_path,
                template,
                {
                    "entity_id": entity_id,
                    "entity_type": entity_type,
                    "canonical_name": canonical_name,
                    "created": datetime.now(tz=UTC).strftime("%Y-%m-%d"),
                },
            )

        # Build auto-section content from claims + evidence
        auto_sections = self._build_auto_sections(
            entity_id, claims, evidence
        )

        # Write auto sections (human sections preserved by update_auto_sections)
        update_auto_sections(page_path, auto_sections)

        return page_path.read_text()

    def _load_template(self, entity_type: str) -> str:
        """Load template for entity type, falling back to _fallback.md."""
        path = self.template_dir / f"{entity_type}.md"
        if not path.exists():
            path = self.template_dir / "_fallback.md"
        if not path.exists():
            raise FileNotFoundError(
                f"No template for {entity_type!r} and no _fallback.md"
            )
        return path.read_text()

    def _build_auto_sections(
        self,
        entity_id: str,
        claims: ClaimCollection,
        evidence: EvidenceStore,
    ) -> dict[str, str]:
        """Build all auto-section content deterministically."""
        sections: dict[str, str] = {}

        # Properties — from EntityClaims about this entity
        sections["properties"] = self._render_properties(entity_id, claims)

        # Linked Entities — from RelationClaims involving this entity
        sections["linked-entities"] = self._render_linked_entities(
            entity_id, claims
        )

        # Evidence — tabular view of supporting evidence
        sections["evidence"] = self._render_evidence(
            entity_id, claims, evidence
        )

        # Contradictions — disputed or contradicting claims
        sections["contradictions"] = self._render_contradictions(
            entity_id, claims
        )

        # Provenance — source tracking
        sections["provenance"] = self._render_provenance(claims, evidence)

        # Last Updated
        sections["last-updated"] = datetime.now(tz=UTC).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        return sections

    def _render_properties(
        self, entity_id: str, claims: ClaimCollection
    ) -> str:
        """Render entity property claims as a markdown table."""
        entity_claims = sorted(
            [ec for ec in claims.entity_claims if ec.entity_id == entity_id],
            key=lambda c: (c.property_name, c.claim_id),
        )
        if not entity_claims:
            return "_No properties extracted._"

        lines = [
            "| Property | Value | Confidence | Status |",
            "|----------|-------|------------|--------|",
        ]
        for ec in entity_claims:
            lines.append(
                f"| {ec.property_name} | {ec.property_value} "
                f"| {ec.confidence:.2f} | {ec.status} |"
            )
        return "\n".join(lines)

    def _render_linked_entities(
        self, entity_id: str, claims: ClaimCollection
    ) -> str:
        """Render relation claims as a markdown table."""
        relations = sorted(
            [
                rc
                for rc in claims.relation_claims
                if rc.source_entity_id == entity_id
                or rc.target_entity_id == entity_id
            ],
            key=lambda c: (c.relation_type, c.claim_id),
        )
        if not relations:
            return "_No linked entities._"

        lines = [
            "| Relation | Entity | Direction | Confidence |",
            "|----------|--------|-----------|------------|",
        ]
        for rc in relations:
            if rc.source_entity_id == entity_id:
                other = rc.target_entity_id
                direction = "outgoing"
            else:
                other = rc.source_entity_id
                direction = "incoming"
            lines.append(
                f"| {rc.relation_type} | {other} "
                f"| {direction} | {rc.confidence:.2f} |"
            )
        return "\n".join(lines)

    def _render_evidence(
        self,
        entity_id: str,
        claims: ClaimCollection,
        evidence: EvidenceStore,
    ) -> str:
        """Render evidence table from all claims about this entity."""
        # Collect all claims relevant to this entity
        relevant: list[Claim] = []
        relevant.extend(
            ec for ec in claims.entity_claims if ec.entity_id == entity_id
        )
        relevant.extend(
            rc
            for rc in claims.relation_claims
            if rc.source_entity_id == entity_id
            or rc.target_entity_id == entity_id
        )
        # Also include general claims from the same document
        relevant.extend(claims.claims)

        if not relevant:
            return "_No evidence._"

        # Sort for determinism
        relevant.sort(key=lambda c: c.claim_id)

        lines = [
            "| Source | Claim | Confidence | Extracted |",
            "|--------|-------|------------|-----------|",
        ]
        for claim in relevant:
            extracted = claim.extracted_at.strftime("%Y-%m-%d")
            lines.append(
                f"| {claim.source_doc_id} | {claim.statement} "
                f"| {claim.confidence:.2f} | {extracted} |"
            )
        return "\n".join(lines)

    def _render_contradictions(
        self, entity_id: str, claims: ClaimCollection
    ) -> str:
        """Render disputed or contradicting claims."""
        disputed: list[Claim] = []
        all_claims: list[Claim] = [
            *claims.claims,
            *claims.entity_claims,
            *claims.relation_claims,
        ]
        for c in all_claims:
            if c.status != ClaimStatus.DISPUTED:
                continue
            # Check if claim is relevant to entity
            if isinstance(c, EntityClaim) and c.entity_id == entity_id:
                disputed.append(c)
            elif isinstance(c, RelationClaim) and (
                c.source_entity_id == entity_id
                or c.target_entity_id == entity_id
            ):
                disputed.append(c)
            elif not isinstance(c, (EntityClaim, RelationClaim)):
                disputed.append(c)

        if not disputed:
            return "_No contradictions detected._"

        disputed.sort(key=lambda c: c.claim_id)

        lines = [
            "| Claim | Status | Confidence | Source |",
            "|-------|--------|------------|--------|",
        ]
        for c in disputed:
            lines.append(
                f"| {c.statement} | {c.status} "
                f"| {c.confidence:.2f} | {c.source_doc_id} |"
            )
        return "\n".join(lines)

    def _render_provenance(
        self, claims: ClaimCollection, evidence: EvidenceStore
    ) -> str:
        """Render provenance table from evidence store."""
        if not evidence.chunks:
            return "_No provenance records._"

        lines = [
            "| Source Document | Chunk | Confidence | Extracted |",
            "|----------------|-------|------------|-----------|",
        ]
        # Gather best confidence per chunk from claims
        chunk_confidence: dict[str, float] = {}
        all_claims: list[Claim] = [
            *claims.claims,
            *claims.entity_claims,
            *claims.relation_claims,
        ]
        for claim in all_claims:
            for cid in claim.evidence_chunk_ids:
                current = chunk_confidence.get(cid, 0.0)
                chunk_confidence[cid] = max(current, claim.confidence)

        for chunk in evidence.chunks:
            conf = chunk_confidence.get(chunk.chunk_id, 0.0)
            extracted = evidence.document.ingested_at.strftime("%Y-%m-%d")
            lines.append(
                f"| {evidence.document.doc_id} | {chunk.chunk_id} "
                f"| {conf:.2f} | {extracted} |"
            )
        return "\n".join(lines)
