"""Literature source server — aggregates corpus, wiki, and graph tools.

In Step 1 of the V2 lab-knowledge plan the literature source owns everything
(papers + wiki + graph). When the lab source server lands in Step 2, lab will
take over its slice (SOPs, meetings, internal reports) and literature will
shrink to the published-literature surface.

For now this module is a thin aggregator over the existing monolithic servers
(``corpus_io``, ``wiki_io``, ``graph_io``). The tool implementations live in
those modules; literature.py registers them on a single FastMCP app named
``literature`` so the new federated pool can spawn one source process per
knowledge domain instead of three.

Why not move the implementations here? Two reasons:

1. The 23 tool functions are already used directly by tests and pipeline code
   that import them by their old module paths (e.g.,
   ``from llm_rag.mcp.corpus_io import search_chunks``). Moving them would
   force a wide-blast-radius rename. The aggregator pattern lets us add the
   federation surface without disturbing any caller.
2. Step 2 will split corpus tools by source (literature vs lab). Doing the
   physical move in Step 1 only to re-shuffle in Step 2 wastes work.

This is the v0.1 ``literature`` source per the federation contract. Run it
standalone with ``python -m llm_rag.mcp.sources.literature``; or have the
``MCPPool`` spawn it via the entry in ``config/mcp-sources.yaml``.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

# Import every tool function from the three monolithic modules.
# They are decorated with @app.tool() on their respective modules' apps,
# but the underlying functions are also importable and callable as plain
# async functions, which is what we need for re-registration.
from llm_rag.mcp.corpus_io import (
    get_chunks as _corpus_get_chunks,
)
from llm_rag.mcp.corpus_io import (
    get_export as _corpus_get_export,
)
from llm_rag.mcp.corpus_io import (
    get_manifest as _corpus_get_manifest,
)
from llm_rag.mcp.corpus_io import (
    ingest_file as _corpus_ingest_file,
)
from llm_rag.mcp.corpus_io import (
    list_pending_docs as _corpus_list_pending_docs,
)
from llm_rag.mcp.corpus_io import (
    save_export as _corpus_save_export,
)
from llm_rag.mcp.corpus_io import (
    save_manifest as _corpus_save_manifest,
)
from llm_rag.mcp.corpus_io import (
    scan_pending_files as _corpus_scan_pending_files,
)
from llm_rag.mcp.corpus_io import (
    search_chunks as _corpus_search_chunks,
)
from llm_rag.mcp.graph_io import (
    get_canonical as _graph_get_canonical,
)
from llm_rag.mcp.graph_io import (
    get_entity as _graph_get_entity,
)
from llm_rag.mcp.graph_io import (
    get_neighbors as _graph_get_neighbors,
)
from llm_rag.mcp.graph_io import (
    list_entities as _graph_list_entities,
)
from llm_rag.mcp.graph_io import (
    materialize_from_claims as _graph_materialize_from_claims,
)
from llm_rag.mcp.graph_io import (
    merge_by_doc_id as _graph_merge_by_doc_id,
)
from llm_rag.mcp.graph_io import (
    merge_extraction as _graph_merge_extraction,
)
from llm_rag.mcp.wiki_io import (
    create_page as _wiki_create_page,
)
from llm_rag.mcp.wiki_io import (
    get_template as _wiki_get_template,
)
from llm_rag.mcp.wiki_io import (
    list_pages as _wiki_list_pages,
)
from llm_rag.mcp.wiki_io import (
    materialize_page as _wiki_materialize_page,
)
from llm_rag.mcp.wiki_io import (
    read_page as _wiki_read_page,
)
from llm_rag.mcp.wiki_io import (
    write_auto_sections as _wiki_write_auto_sections,
)
from llm_rag.mcp.wiki_io import (
    write_provenance as _wiki_write_provenance,
)

app = FastMCP("literature")


# Re-register each tool on the literature app. Tool names stay identical so
# any caller using the federated source server gets the same MCP-level API.
app.tool()(_corpus_get_chunks)
app.tool()(_corpus_get_manifest)
app.tool()(_corpus_save_manifest)
app.tool()(_corpus_save_export)
app.tool()(_corpus_list_pending_docs)
app.tool()(_corpus_get_export)
app.tool()(_corpus_ingest_file)
app.tool()(_corpus_scan_pending_files)
app.tool()(_corpus_search_chunks)

app.tool()(_wiki_read_page)
app.tool()(_wiki_write_auto_sections)
app.tool()(_wiki_list_pages)
app.tool()(_wiki_get_template)
app.tool()(_wiki_create_page)
app.tool()(_wiki_write_provenance)
app.tool()(_wiki_materialize_page)

app.tool()(_graph_get_entity)
app.tool()(_graph_list_entities)
app.tool()(_graph_merge_extraction)
app.tool()(_graph_merge_by_doc_id)
app.tool()(_graph_materialize_from_claims)
app.tool()(_graph_get_neighbors)
app.tool()(_graph_get_canonical)


def main() -> None:
    """Entry point for ``python -m llm_rag.mcp.sources.literature`` / pyproject script."""
    app.run()


if __name__ == "__main__":
    main()
