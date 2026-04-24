from __future__ import annotations

from pathlib import Path

from llm_rag.wiki.reader import parse_page


def make_wiki_page(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "lfp.md"
    p.write_text(content)
    return p


def test_parse_page_extracts_auto_section(tmp_path: Path) -> None:
    p = make_wiki_page(tmp_path, """\
---
entity_type: material
entity_id: "material:lfp"
canonical_name: "LFP"
---

# LFP

<!-- auto-start: evidence -->
| Source | Claim |
|--------|-------|
| doc.md | LFP 170 mAh/g |
<!-- auto-end: evidence -->
""")
    page = parse_page(p)
    assert "evidence" in page.sections
    assert page.sections["evidence"].managed_by == "auto"
    assert "LFP 170" in page.sections["evidence"].content


def test_parse_page_extracts_human_section(tmp_path: Path) -> None:
    p = make_wiki_page(tmp_path, """\
---
entity_type: material
entity_id: "material:lfp"
canonical_name: "LFP"
---

<!-- human-start: summary -->
LFP is a stable cathode.
<!-- human-end: summary -->
""")
    page = parse_page(p)
    assert "summary" in page.sections
    assert page.sections["summary"].managed_by == "human"
    assert "stable cathode" in page.sections["summary"].content


def test_parse_page_reads_frontmatter(tmp_path: Path) -> None:
    p = make_wiki_page(tmp_path, """\
---
entity_type: material
entity_id: "material:lfp"
canonical_name: "LFP"
---
""")
    page = parse_page(p)
    assert page.entity_id == "material:lfp"
    assert page.canonical_name == "LFP"
    assert page.page_type == "material"


def test_parse_page_empty_sections(tmp_path: Path) -> None:
    p = make_wiki_page(tmp_path, """\
---
entity_type: material
entity_id: "material:lfp"
canonical_name: "LFP"
---

<!-- auto-start: evidence -->
<!-- auto-end: evidence -->
""")
    page = parse_page(p)
    assert "evidence" in page.sections
    assert page.sections["evidence"].content == ""


def test_parse_page_mixed_sections(tmp_path: Path) -> None:
    p = make_wiki_page(tmp_path, """\
---
entity_type: material
entity_id: "material:lfp"
canonical_name: "LFP"
---

<!-- auto-start: evidence -->
row1
<!-- auto-end: evidence -->

<!-- human-start: open-questions -->
What about rate capability?
<!-- human-end: open-questions -->
""")
    page = parse_page(p)
    assert len(page.sections) == 2
    assert page.sections["evidence"].managed_by == "auto"
    assert page.sections["open-questions"].managed_by == "human"
