from __future__ import annotations

from llm_rag.graph.store import GraphStore
from llm_rag.schemas.entities import ExtractionResult


def merge_extraction_result(result: ExtractionResult, store: GraphStore) -> None:
    """Merge an ExtractionResult into the GraphStore.

    Adds all entities and relations from the extraction result into the store's
    NetworkX graph. This is used during the pipeline to accumulate knowledge
    from multiple documents into a single graph.

    Args:
        result: The ExtractionResult containing entities and relations to merge.
        store: The GraphStore to merge into.
    """
    for entity in result.entities:
        store.add_entity(entity)
    for relation in result.relations:
        store.add_relation(relation)
