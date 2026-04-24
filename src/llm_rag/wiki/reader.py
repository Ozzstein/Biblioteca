from __future__ import annotations

import re
from pathlib import Path

import frontmatter

from llm_rag.schemas.wiki import WikiPage, WikiSection

_AUTO_RE = re.compile(
    r"<!-- auto-start: (\S+) -->(.*?)<!-- auto-end: \1 -->",
    re.DOTALL,
)
_HUMAN_RE = re.compile(
    r"<!-- human-start: (\S+) -->(.*?)<!-- human-end: \1 -->",
    re.DOTALL,
)


def parse_page(path: Path) -> WikiPage:
    post = frontmatter.load(str(path))
    meta = post.metadata
    body = post.content
    sections: dict[str, WikiSection] = {}

    for match in _AUTO_RE.finditer(body):
        name, raw = match.group(1), match.group(2).strip()
        sections[name] = WikiSection(name=name, managed_by="auto", content=raw)

    for match in _HUMAN_RE.finditer(body):
        name, raw = match.group(1), match.group(2).strip()
        sections[name] = WikiSection(name=name, managed_by="human", content=raw)

    return WikiPage(
        page_type=str(meta.get("entity_type", "unknown")),
        entity_id=str(meta.get("entity_id", "")),
        canonical_name=str(meta.get("canonical_name", path.stem)),
        path=str(path),
        sections=sections,
    )
