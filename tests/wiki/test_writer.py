from __future__ import annotations

from pathlib import Path

from llm_rag.wiki.writer import create_page, update_auto_sections

_TEMPLATE = """\
---
entity_type: material
entity_id: "{{ entity_id }}"
canonical_name: "{{ canonical_name }}"
---

# {{ canonical_name }}

<!-- auto-start: evidence -->
<!-- auto-end: evidence -->

<!-- human-start: summary -->
original human content
<!-- human-end: summary -->
"""


def test_update_auto_section_replaces_content(tmp_path: Path) -> None:
    p = tmp_path / "lfp.md"
    p.write_text(_TEMPLATE)
    update_auto_sections(p, {"evidence": "| Source | Claim |\n|---|---|\n| doc | LFP |"})
    result = p.read_text()
    assert "| Source | Claim |" in result
    assert "<!-- auto-start: evidence -->" in result
    assert "<!-- auto-end: evidence -->" in result


def test_update_auto_section_preserves_human_section(tmp_path: Path) -> None:
    p = tmp_path / "lfp.md"
    p.write_text(_TEMPLATE)
    update_auto_sections(p, {"evidence": "new content"})
    result = p.read_text()
    assert "original human content" in result


def test_update_auto_section_empty_content(tmp_path: Path) -> None:
    p = tmp_path / "lfp.md"
    p.write_text(_TEMPLATE)
    update_auto_sections(p, {"evidence": ""})
    result = p.read_text()
    # Tags still present, content between them is empty
    assert "<!-- auto-start: evidence -->" in result
    assert "<!-- auto-end: evidence -->" in result


def test_create_page_renders_template(tmp_path: Path) -> None:
    p = tmp_path / "wiki" / "materials" / "lfp.md"
    create_page(p, _TEMPLATE, {"entity_id": "material:lfp", "canonical_name": "LFP"})
    assert p.exists()
    content = p.read_text()
    assert 'entity_id: "material:lfp"' in content
    assert "# LFP" in content


def test_create_page_skips_existing(tmp_path: Path) -> None:
    p = tmp_path / "lfp.md"
    p.write_text("existing content")
    create_page(p, _TEMPLATE, {"entity_id": "x", "canonical_name": "X"})
    assert p.read_text() == "existing content"
