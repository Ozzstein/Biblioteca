from __future__ import annotations

from pathlib import Path

from llm_rag.wiki.reader import parse_page
from llm_rag.wiki.writer import update_auto_sections

_TEMPLATE = """\
---
entity_type: material
entity_id: "material:lfp"
canonical_name: "LFP"
---

# LFP

## Evidence (Literature)
<!-- auto-start: evidence-literature -->
<!-- auto-end: evidence-literature -->

## Evidence (Lab)
<!-- auto-start: evidence-lab -->
<!-- auto-end: evidence-lab -->
"""


def test_per_source_sections_coexist_without_collision(tmp_path: Path) -> None:
    page = tmp_path / "lfp.md"
    page.write_text(_TEMPLATE)

    update_auto_sections(page, {"evidence-literature": "lit row"})
    update_auto_sections(page, {"evidence-lab": "lab row"})

    text = page.read_text()
    assert "lit row" in text
    assert "lab row" in text


def test_reader_exposes_merged_evidence_view(tmp_path: Path) -> None:
    page = tmp_path / "lfp.md"
    page.write_text(_TEMPLATE)

    update_auto_sections(page, {"evidence-literature": "lit row"})
    update_auto_sections(page, {"evidence-lab": "lab row"})

    parsed = parse_page(page)
    assert "evidence" in parsed.sections
    assert "lit row" in parsed.sections["evidence"].content
    assert "lab row" in parsed.sections["evidence"].content
