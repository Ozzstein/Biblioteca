from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from filelock import FileLock, Timeout

from llm_rag.mcp.gateway import create_app
from llm_rag.wiki import writer
from tests.mcp.gateway_helpers import FakePool, FakeSession, allow_auth

_TEMPLATE = """# LFP
<!-- auto-start: evidence-literature -->
old lit
<!-- auto-end: evidence-literature -->
<!-- auto-start: evidence-lab -->
old lab
<!-- auto-end: evidence-lab -->
"""


def test_concurrent_writers_serialize_without_lost_updates(tmp_path: Path) -> None:
    page = tmp_path / "wiki" / "materials" / "lfp.md"
    page.parent.mkdir(parents=True)
    page.write_text(_TEMPLATE)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(writer.update_auto_sections, page, {"evidence-literature": "lit row"}),
            executor.submit(writer.update_auto_sections, page, {"evidence-lab": "lab row"}),
        ]
        for future in futures:
            future.result()

    content = page.read_text()
    assert "lit row" in content
    assert "lab row" in content
    assert "<!-- auto-start: evidence-literature -->" in content
    assert "<!-- auto-end: evidence-lab -->" in content


def test_lock_timeout_propagates_from_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = tmp_path / "wiki" / "materials" / "lfp.md"
    page.parent.mkdir(parents=True)
    page.write_text(_TEMPLATE)
    real_lock = FileLock

    def short_lock(lock_file: str, timeout: float) -> FileLock:
        return real_lock(lock_file, timeout=0.01)

    monkeypatch.setattr(writer, "FileLock", short_lock)

    with real_lock(str(page) + ".lock", timeout=1):
        with pytest.raises(Timeout):
            writer.update_auto_sections(page, {"evidence-literature": "new"})


def test_gateway_maps_filelock_timeout_to_503() -> None:
    pool = FakePool(
        sessions={
            "literature": FakeSession(exc=Timeout("wiki lock")),
            "lab": FakeSession(),
        }
    )
    app = create_app(pool_factory=lambda: pool)
    allow_auth(app)

    with TestClient(app) as client:
        response = client.post(
            "/mcp/literature/write_auto_sections",
            json={"relative_path": "materials/lfp.md", "sections": {"evidence": "x"}},
        )

    assert response.status_code == 503
