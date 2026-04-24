from llm_rag.utils.chunking import chunk_text


def test_short_text_is_single_chunk():
    chunks = chunk_text("hello world", doc_id="test-001")
    assert len(chunks) == 1
    assert chunks[0].text == "hello world"
    assert chunks[0].chunk_index == 0
    assert chunks[0].doc_id == "test-001"


def test_empty_text_returns_no_chunks():
    chunks = chunk_text("", doc_id="test-001")
    assert chunks == []


def test_long_text_produces_multiple_chunks():
    text = "word " * 1500  # ~7500 chars
    chunks = chunk_text(text, doc_id="test", chunk_size=512, overlap=64)
    assert len(chunks) >= 2


def test_chunks_are_indexed_sequentially():
    text = "A" * 5000
    chunks = chunk_text(text, doc_id="test", chunk_size=512, overlap=64)
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i


def test_chunks_overlap():
    text = "A" * 6000
    chunks = chunk_text(text, doc_id="test", chunk_size=512, overlap=64)
    char_overlap = 64 * 4
    assert chunks[0].text[-char_overlap:] == chunks[1].text[:char_overlap]


def test_chunk_carries_section_and_page():
    chunks = chunk_text("some text", doc_id="x", section="§3.2", page=5)
    assert chunks[0].section == "§3.2"
    assert chunks[0].page == 5


def test_chunk_section_defaults_none():
    chunks = chunk_text("some text", doc_id="x")
    assert chunks[0].section is None
    assert chunks[0].page is None


def test_token_count_is_approximate():
    text = "A" * 400  # 400 chars ≈ 100 tokens
    chunks = chunk_text(text, doc_id="x")
    assert chunks[0].token_count == 100
