from pathlib import Path

from llm_rag.utils.hashing import content_hash


def test_hash_is_deterministic(tmp_path: Path):
    f = tmp_path / "test.txt"
    f.write_text("hello battery research")
    assert content_hash(f) == content_hash(f)


def test_hash_changes_with_content(tmp_path: Path):
    f = tmp_path / "test.txt"
    f.write_text("hello")
    h1 = content_hash(f)
    f.write_text("goodbye")
    h2 = content_hash(f)
    assert h1 != h2


def test_hash_format(tmp_path: Path):
    f = tmp_path / "test.txt"
    f.write_text("test")
    h = content_hash(f)
    assert h.startswith("sha256:")
    assert len(h) == 7 + 64


def test_hash_works_on_binary(tmp_path: Path):
    f = tmp_path / "test.bin"
    f.write_bytes(b"\x00\x01\x02\xff")
    h = content_hash(f)
    assert h.startswith("sha256:")


def test_different_files_different_hashes(tmp_path: Path):
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_text("content A")
    f2.write_text("content B")
    assert content_hash(f1) != content_hash(f2)
