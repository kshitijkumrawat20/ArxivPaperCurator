from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.indexing.hybrid_indexer import HybridIndexingService
from src.services.indexing.text_chunker import TextChunker


@pytest.mark.asyncio
async def test_index_paper_bulk_indexes_all_chunks_once():
    chunks = [
        SimpleNamespace(
            text=f"chunk {index}",
            metadata=SimpleNamespace(
                chunk_index=index,
                word_count=2,
                start_char=index * 10,
                end_char=index * 10 + 8,
            ),
        )
        for index in range(3)
    ]
    chunker = MagicMock()
    chunker.chunk_paper.return_value = chunks
    embeddings = AsyncMock()
    embeddings.embed_passages.return_value = [[index] for index in range(3)]
    opensearch = MagicMock()
    opensearch.bulk_index_chunks.return_value = {"success": 3, "failed": 0}

    service = HybridIndexingService(chunker, embeddings, opensearch)

    result = await service.index_paper(
        {
            "id": "db-paper-1",
            "arxiv_id": "2501.00001",
            "title": "A test paper",
            "abstract": "A short abstract",
            "authors": ["A. Author"],
            "categories": ["cs.AI"],
        }
    )

    assert result == {
        "chunks_created": 3,
        "chunks_indexed": 3,
        "embeddings_generated": 3,
        "error": 0,
    }
    opensearch.bulk_index_chunks.assert_called_once()
    indexed_chunks = opensearch.bulk_index_chunks.call_args.args[0]
    assert [item["chunk_data"]["chunk_text"] for item in indexed_chunks] == ["chunk 0", "chunk 1", "chunk 2"]
    assert [item["embedding"] for item in indexed_chunks] == [[0], [1], [2]]


def test_short_text_chunk_uses_reconstructed_words():
    chunker = TextChunker(chunk_size=20, overlap_size=5, min_chunk_size=10)

    chunks = chunker.chunk_text("  a short   abstract text  ", "2501.00001", "db-paper-1")

    assert len(chunks) == 1
    assert chunks[0].text == "a short abstract text"
    assert chunks[0].metadata.word_count == 4


def test_chunk_paper_uses_abstract_when_full_text_is_missing():
    chunker = TextChunker(chunk_size=20, overlap_size=5, min_chunk_size=10)

    chunks = chunker.chunk_paper(
        title="Abstract-only paper",
        abstract="This abstract describes a useful research method.",
        full_text="",
        arxiv_id="2501.00001",
        paper_id="db-paper-1",
    )

    assert len(chunks) == 1
    assert chunks[0].text == "This abstract describes a useful research method."
    assert chunks[0].metadata.word_count == 7
