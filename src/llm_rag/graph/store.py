from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from llm_rag.schemas.entities import Entity, Relation

__all__ = ["GraphStore"]


class GraphStore:
    """NetworkX MultiDiGraph wrapper for entity-relation graph storage and retrieval."""

    def __init__(self, snapshot_path: Path) -> None:
        """Initialize GraphStore with a path for GraphML snapshots.

        Args:
            snapshot_path: Path where GraphML snapshots are saved/loaded.
        """
        self.snapshot_path = snapshot_path
        self._g: nx.MultiDiGraph = nx.MultiDiGraph()

    def load(self) -> None:
        """Load the graph from a GraphML file if it exists."""
        if self.snapshot_path.exists():
            self._g = nx.read_graphml(str(self.snapshot_path), force_multigraph=True)

    def save(self) -> None:
        """Save the current graph to a GraphML file."""
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        nx.write_graphml(self._g, str(self.snapshot_path))

    def add_entity(
        self,
        entity: Entity,
        evidence_chunk_ids: list[str] | None = None,
    ) -> None:
        """Add an entity node to the graph.

        Args:
            entity: The Entity to add.
            evidence_chunk_ids: Optional list of chunk IDs that support this entity.
        """
        source_doc_ids = list({p.source_doc_id for p in entity.provenance})
        confidences = [p.confidence for p in entity.provenance]
        timestamps = [p.timestamp for p in entity.provenance]

        self._g.add_node(
            entity.entity_id,
            entity_type=entity.entity_type.value,
            canonical_name=entity.canonical_name,
            aliases=json.dumps(entity.aliases),
            source_doc_ids=json.dumps(source_doc_ids),
            evidence_chunk_ids=json.dumps(evidence_chunk_ids or []),
            confidence=max(confidences) if confidences else 0.0,
            created_at=min(timestamps).isoformat() if timestamps else "",
            updated_at=max(timestamps).isoformat() if timestamps else "",
        )

    def add_relation(self, relation: Relation) -> None:
        """Add a relation edge to the graph.

        Args:
            relation: The Relation to add.
        """
        source_doc_ids = list({p.source_doc_id for p in relation.provenance})
        confidences = [p.confidence for p in relation.provenance]

        self._g.add_edge(
            relation.source_entity_id,
            relation.target_entity_id,
            key=relation.relation_id,
            relation_type=relation.relation_type.value,
            weight=relation.weight,
            source_doc_ids=json.dumps(source_doc_ids),
            confidence=max(confidences) if confidences else 0.0,
        )

    def has_node(self, entity_id: str) -> bool:
        """Check if an entity node exists in the graph.

        Args:
            entity_id: The entity ID to check.

        Returns:
            True if the node exists, False otherwise.
        """
        return bool(self._g.has_node(entity_id))

    def node_count(self) -> int:
        """Get the total number of nodes in the graph.

        Returns:
            Number of entities in the graph.
        """
        return int(self._g.number_of_nodes())

    def edge_count(self) -> int:
        """Get the total number of edges in the graph.

        Returns:
            Number of relations in the graph.
        """
        return int(self._g.number_of_edges())

    def neighbors(self, entity_id: str) -> list[str]:
        """Get all out-neighbors of a given entity.

        Args:
            entity_id: The entity ID.

        Returns:
            List of entity IDs that this entity points to.
        """
        return list(self._g.neighbors(entity_id))
