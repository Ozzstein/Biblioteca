"""Graph materializer — builds a NetworkX graph as a projection from claims/facts.

The graph is derived data, not a primary system of record.  Given a set of
``EntityClaim`` and ``RelationClaim`` objects (or a ``ClaimCollection``), the
materializer produces a deterministic ``nx.MultiDiGraph`` with canonical entity
nodes and relation edges.
"""

from __future__ import annotations

from pathlib import Path

import networkx as nx

from llm_rag.graph.normalization import (
    canonicalize_relation_endpoints,
    load_normalization_map,
    normalize_entity_id,
)
from llm_rag.knowledge.models import (
    ClaimCollection,
    EntityClaim,
    RelationClaim,
)


class GraphMaterializer:
    """Builds a NetworkX graph that is fully derivable from claims and facts.

    Parameters
    ----------
    alias_map:
        Optional pre-loaded alias → canonical-ID mapping.  When *None* (the
        default), entity IDs are used as-is without normalization.
    """

    def __init__(self, alias_map: dict[str, str] | None = None) -> None:
        self._alias_map: dict[str, str] = alias_map or {}

    # ------------------------------------------------------------------
    # Public helpers to load alias map from YAML
    # ------------------------------------------------------------------

    @classmethod
    def from_normalization_yaml(cls, yaml_path: Path) -> GraphMaterializer:
        """Create a materializer with alias resolution from a YAML file."""
        alias_map = load_normalization_map(yaml_path)
        return cls(alias_map=alias_map)

    # ------------------------------------------------------------------
    # Core projection methods
    # ------------------------------------------------------------------

    def build_graph_from_claims(
        self,
        entity_claims: list[EntityClaim],
        relation_claims: list[RelationClaim],
    ) -> nx.MultiDiGraph:
        """Materialize a graph from raw entity and relation claims.

        All claims are included regardless of confidence or status.
        Output is deterministic: nodes and edges are added in sorted order of
        their canonical IDs.
        """
        g = nx.MultiDiGraph()
        self._add_entity_claims(g, entity_claims)
        self._add_relation_claims(g, relation_claims)
        return g

    def build_graph_from_facts(
        self,
        entity_claims: list[EntityClaim],
        relation_claims: list[RelationClaim],
    ) -> nx.MultiDiGraph:
        """Materialize a graph from *facts only* (high-confidence, well-evidenced claims).

        A claim qualifies as a fact when ``confidence >= 0.9`` **and** it has at
        least 2 evidence chunk IDs.  This mirrors the ``Fact`` promotion rules
        in ``llm_rag.knowledge.models``.
        """
        fact_entities = [
            ec
            for ec in entity_claims
            if ec.confidence >= 0.9 and len(ec.evidence_chunk_ids) >= 2
        ]
        fact_relations = [
            rc
            for rc in relation_claims
            if rc.confidence >= 0.9 and len(rc.evidence_chunk_ids) >= 2
        ]
        return self.build_graph_from_claims(fact_entities, fact_relations)

    def build_graph_from_collection(
        self,
        collection: ClaimCollection,
        *,
        facts_only: bool = False,
    ) -> nx.MultiDiGraph:
        """Convenience wrapper that accepts a ``ClaimCollection``.

        Parameters
        ----------
        collection:
            The claim collection to materialize.
        facts_only:
            If *True*, only claims that qualify as facts are included.
        """
        if facts_only:
            return self.build_graph_from_facts(
                collection.entity_claims,
                collection.relation_claims,
            )
        return self.build_graph_from_claims(
            collection.entity_claims,
            collection.relation_claims,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve(self, entity_id: str) -> str:
        if self._alias_map:
            return normalize_entity_id(entity_id, self._alias_map)
        return entity_id

    def _add_entity_claims(
        self,
        g: nx.MultiDiGraph,
        claims: list[EntityClaim],
    ) -> None:
        # Sort for deterministic output
        sorted_claims = sorted(claims, key=lambda c: (c.entity_id, c.claim_id))

        for ec in sorted_claims:
            canonical_id = self._resolve(ec.entity_id)
            if g.has_node(canonical_id):
                # Merge: update confidence to max, accumulate evidence
                attrs = g.nodes[canonical_id]
                attrs["confidence"] = max(attrs["confidence"], ec.confidence)
                existing_chunks: set[str] = set(attrs.get("evidence_chunk_ids", "").split(",")) - {""}
                existing_chunks.update(ec.evidence_chunk_ids)
                attrs["evidence_chunk_ids"] = ",".join(sorted(existing_chunks))
                existing_docs: set[str] = set(attrs.get("source_doc_ids", "").split(",")) - {""}
                existing_docs.add(ec.source_doc_id)
                attrs["source_doc_ids"] = ",".join(sorted(existing_docs))
                # Append property
                props_key = f"prop:{ec.property_name}"
                existing_val = attrs.get(props_key, "")
                if ec.property_value not in existing_val:
                    attrs[props_key] = (
                        f"{existing_val};{ec.property_value}" if existing_val else ec.property_value
                    )
            else:
                g.add_node(
                    canonical_id,
                    entity_type=ec.entity_type.value,
                    confidence=ec.confidence,
                    evidence_chunk_ids=",".join(sorted(ec.evidence_chunk_ids)),
                    source_doc_ids=ec.source_doc_id,
                    status=ec.status.value,
                    **{f"prop:{ec.property_name}": ec.property_value},
                )

    def _add_relation_claims(
        self,
        g: nx.MultiDiGraph,
        claims: list[RelationClaim],
    ) -> None:
        sorted_claims = sorted(
            claims,
            key=lambda c: (c.source_entity_id, c.target_entity_id, c.claim_id),
        )

        for rc in sorted_claims:
            src, tgt = rc.source_entity_id, rc.target_entity_id
            if self._alias_map:
                src, tgt = canonicalize_relation_endpoints(src, tgt, self._alias_map)

            # Ensure endpoint nodes exist (as minimal stubs)
            if not g.has_node(src):
                g.add_node(src, entity_type="", confidence=0.0)
            if not g.has_node(tgt):
                g.add_node(tgt, entity_type="", confidence=0.0)

            g.add_edge(
                src,
                tgt,
                key=rc.claim_id,
                relation_type=rc.relation_type.value,
                confidence=rc.confidence,
                source_doc_id=rc.source_doc_id,
                evidence_chunk_ids=",".join(sorted(rc.evidence_chunk_ids)),
                status=rc.status.value,
            )
