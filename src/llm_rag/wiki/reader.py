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
_SOURCE_SECTION_RE = re.compile(r"^(?P<base>[a-z0-9-]+)-(?P<source>[a-z0-9-]+)$")
_SOURCE_VARIANT_BASES = {"evidence"}


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

    # Merge source-scoped auto sections into a synthetic base section.
    # Example: evidence-literature + evidence-lab => evidence
    merged: dict[str, list[str]] = {}
    for section in sections.values():
        if section.managed_by != "auto":
            continue
        m = _SOURCE_SECTION_RE.match(section.name)
        if not m:
            continue
        base = m.group("base")
        if base not in _SOURCE_VARIANT_BASES:
            continue
        source = m.group("source")
        rendered = f"### {source}\\n\\n{section.content}".strip()
        merged.setdefault(base, []).append(rendered)

    for base, parts in merged.items():
        if base in sections:
            continue
        sections[base] = WikiSection(
            name=base,
            managed_by="auto",
            content="\\n\\n".join(parts).strip(),
        )

    return WikiPage(
        page_type=str(meta.get("entity_type", "unknown")),
        entity_id=str(meta.get("entity_id", "")),
        canonical_name=str(meta.get("canonical_name", path.stem)),
        path=str(path),
        sections=sections,
    )


def resolve_sop_versions(
    wiki_dir: Path,
    sop_id: str,
    *,
    include_history: bool = False,
) -> list[Path]:
    """Resolve SOP markdown paths from sop index frontmatter.

    Returns only the current version by default, or all declared versions when
    ``include_history=True``.
    """
    base = wiki_dir / "sop" / sop_id
    index_path = base / "index.md"
    if not index_path.exists():
        return []

    post = frontmatter.load(str(index_path))
    current_version = str(post.metadata.get("current_version", "")).strip()
    declared_versions = post.metadata.get("versions", [])
    versions = (
        [str(v).strip() for v in declared_versions if str(v).strip()]
        if include_history
        else [current_version] if current_version else []
    )
    out: list[Path] = []
    for version in versions:
        path = base / f"{version}.md"
        if path.exists():
            out.append(path)
    return out
