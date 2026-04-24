"""Test that wiki page templates cover all entity types."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from llm_rag.config import get_settings
from llm_rag.schemas.entities import EntityType

# Mapping from EntityType to expected template filename.
# Some entity types share a template or map to a non-obvious name;
# entity types without a dedicated template are listed so the test
# explicitly flags the gap.
ENTITY_TYPE_TO_TEMPLATE: dict[EntityType, str] = {
    EntityType.MATERIAL: "material.md",
    EntityType.PROCESS: "process.md",
    EntityType.DATASET: "dataset.md",
    EntityType.PROJECT: "project.md",
    EntityType.CLAIM: "synthesis.md",
    EntityType.FAILURE_MECHANISM: "mechanism.md",
    EntityType.TEST_CONDITION: "test.md",
    EntityType.EXPERIMENT: "test.md",
    EntityType.METRIC: "test.md",
    EntityType.DOCUMENT: "document.md",
    EntityType.COMPONENT: "component.md",
    EntityType.FORMULATION: "formulation.md",
    EntityType.CELL: "cell.md",
    EntityType.PROPERTY: "property.md",
}


def _template_dir() -> Path:
    """Return the page-templates directory."""
    settings = get_settings()
    return settings.root_dir / "config" / "page-templates"


class TestTemplateRegistry:
    """Ensure every EntityType has a corresponding wiki template."""

    def test_all_entity_types_have_mapping(self) -> None:
        """Every EntityType enum member must appear in the mapping."""
        missing = set(EntityType) - set(ENTITY_TYPE_TO_TEMPLATE)
        assert not missing, (
            f"EntityType members missing from ENTITY_TYPE_TO_TEMPLATE: {missing}"
        )

    def test_template_files_exist(self) -> None:
        """Every mapped template file must exist on disk."""
        template_dir = _template_dir()
        missing: list[str] = []
        for entity_type, filename in ENTITY_TYPE_TO_TEMPLATE.items():
            path = template_dir / filename
            if not path.exists():
                missing.append(f"{entity_type.value} -> {filename}")
        assert not missing, (
            f"Missing template files in {template_dir}:\n"
            + "\n".join(f"  - {m}" for m in missing)
        )

    def test_no_orphan_templates(self) -> None:
        """Every .md file in page-templates/ should be referenced by at least one entity type (except _fallback.md)."""
        template_dir = _template_dir()
        referenced = set(ENTITY_TYPE_TO_TEMPLATE.values())
        actual = {p.name for p in template_dir.glob("*.md")} - {"_fallback.md"}
        orphans = actual - referenced
        assert not orphans, (
            f"Template files not referenced by any EntityType: {orphans}"
        )

    def test_fallback_template_exists(self) -> None:
        """The _fallback.md template must exist in page-templates/."""
        template_dir = _template_dir()
        assert (template_dir / "_fallback.md").exists()


class TestTemplateProvenanceSections:
    """Ensure every template has a provenance auto section."""

    def test_all_templates_have_provenance_section(self) -> None:
        """Every page template must contain auto-fenced provenance markers."""
        template_dir = _template_dir()
        missing: list[str] = []
        for template_file in sorted(template_dir.glob("*.md")):
            content = template_file.read_text()
            if "<!-- auto-start: provenance -->" not in content:
                missing.append(template_file.name)
        assert not missing, (
            f"Templates missing provenance section: {missing}"
        )


class TestTemplateFallback:
    """Verify fallback template behavior for unknown page types."""

    @pytest.mark.asyncio
    async def test_get_template_uses_fallback_for_unknown_type(self, caplog: pytest.LogCaptureFixture) -> None:
        """get_template returns fallback content and logs a warning for unknown page types."""
        from llm_rag.mcp.wiki_io import get_template

        with caplog.at_level(logging.WARNING, logger="llm_rag.mcp.wiki_io"):
            result = await get_template("nonexistent-type")

        # Should contain fallback template content
        assert "# {{ canonical_name }}" in result
        assert "auto-start: details" in result

        # Should have logged a warning
        assert any("fallback" in r.message.lower() for r in caplog.records)
        assert any("nonexistent-type" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_get_template_still_returns_specific_template(self) -> None:
        """get_template returns the specific template when it exists."""
        from llm_rag.mcp.wiki_io import get_template

        result = await get_template("material")
        assert "entity_type: material" in result

    @pytest.mark.asyncio
    async def test_create_page_uses_fallback_for_unknown_type(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """create_page uses fallback template for unknown page types."""
        from llm_rag.mcp.wiki_io import create_page

        monkeypatch.setenv("ROOT_DIR", str(tmp_path))
        get_settings.cache_clear()
        try:
            # Set up wiki dir and copy fallback template
            settings = get_settings()
            wiki_dir = settings.wiki_dir
            wiki_dir.mkdir(parents=True, exist_ok=True)
            template_dir = settings.config_dir / "page-templates"
            template_dir.mkdir(parents=True, exist_ok=True)

            # Copy fallback template from project config
            project_template_dir = Path(__file__).parent.parent.parent / "config" / "page-templates"
            src_fallback = project_template_dir / "_fallback.md"
            (template_dir / "_fallback.md").write_text(src_fallback.read_text())

            with caplog.at_level(logging.WARNING, logger="llm_rag.mcp.wiki_io"):
                await create_page("test-page.md", "brand-new-type", {"canonical_name": "Test"})

            page_content = (wiki_dir / "test-page.md").read_text()
            assert "# Test" in page_content
            assert any("fallback" in r.message.lower() for r in caplog.records)
        finally:
            get_settings.cache_clear()
