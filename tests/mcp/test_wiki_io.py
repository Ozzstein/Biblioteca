from __future__ import annotations

from pathlib import Path

import pytest

from llm_rag.mcp.wiki_io import (
    create_page,
    get_template,
    list_pages,
    read_page,
    write_auto_sections,
)


@pytest.fixture()
def wiki_dir(tmp_path: Path) -> Path:
    d = tmp_path / "wiki"
    d.mkdir()
    return d


@pytest.fixture()
def templates_dir(tmp_path: Path) -> Path:
    d = tmp_path / "config" / "page-templates"
    d.mkdir(parents=True)
    return d


async def test_read_page_returns_content(wiki_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    (wiki_dir / "materials").mkdir()
    (wiki_dir / "materials" / "lfp.md").write_text("# LFP\nsome content")
    result = await read_page("materials/lfp.md")
    assert "LFP" in result
    get_settings.cache_clear()


async def test_read_page_raises_for_missing(wiki_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    with pytest.raises(FileNotFoundError):
        await read_page("materials/no-such.md")
    get_settings.cache_clear()


async def test_list_pages_returns_relative_paths(wiki_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    (wiki_dir / "materials").mkdir()
    (wiki_dir / "materials" / "lfp.md").write_text("x")
    (wiki_dir / "materials" / "nmc.md").write_text("x")
    result = await list_pages("materials")
    assert "materials/lfp.md" in result
    assert "materials/nmc.md" in result
    get_settings.cache_clear()


async def test_get_template_returns_content(templates_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    (templates_dir / "material.md").write_text("# {{ canonical_name }}")
    result = await get_template("material")
    assert "canonical_name" in result
    get_settings.cache_clear()


async def test_write_auto_sections_updates_fenced_content(wiki_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    (wiki_dir / "materials").mkdir()
    page = wiki_dir / "materials" / "lfp.md"
    page.write_text(
        "# LFP\n"
        "<!-- auto-start: evidence -->\nold content\n<!-- auto-end: evidence -->\n"
    )
    await write_auto_sections("materials/lfp.md", {"evidence": "| new | table |"})
    assert "new | table" in page.read_text()
    assert "old content" not in page.read_text()
    get_settings.cache_clear()


async def test_create_page_writes_template(templates_dir: Path, wiki_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from llm_rag.config import get_settings
    get_settings.cache_clear()
    (templates_dir / "material.md").write_text("# {{ canonical_name }}\n{{ entity_id }}")
    await create_page("materials/new-material.md", "material", {"canonical_name": "NewMat", "entity_id": "material:newmat"})
    created = wiki_dir / "materials" / "new-material.md"
    assert created.exists()
    assert "NewMat" in created.read_text()
    get_settings.cache_clear()
