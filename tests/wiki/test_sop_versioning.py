from __future__ import annotations

from pathlib import Path

from llm_rag.wiki.reader import resolve_sop_versions


def test_resolve_current_sop_version_only_by_default(tmp_path: Path) -> None:
    base = tmp_path / "sop" / "SOP-001"
    base.mkdir(parents=True)
    (base / "v1.md").write_text("# SOP-001 v1")
    (base / "v2.md").write_text("# SOP-001 v2")
    (base / "index.md").write_text(
        """---
sop_id: SOP-001
current_version: v2
versions: [v1, v2]
---
"""
    )

    resolved = resolve_sop_versions(tmp_path, "SOP-001")
    assert resolved == [base / "v2.md"]


def test_resolve_sop_history_when_requested(tmp_path: Path) -> None:
    base = tmp_path / "sop" / "SOP-002"
    base.mkdir(parents=True)
    (base / "v1.md").write_text("# SOP-002 v1")
    (base / "v2.md").write_text("# SOP-002 v2")
    (base / "index.md").write_text(
        """---
sop_id: SOP-002
current_version: v2
versions: [v1, v2]
---
"""
    )

    resolved = resolve_sop_versions(tmp_path, "SOP-002", include_history=True)
    assert resolved == [base / "v1.md", base / "v2.md"]
