import pytest

from src.config import RedisSettings
from src.schema.api.ask import AskRequest, PaperAskRequest, PaperAskResponse
from src.services.cache.client import CacheClient


class MemoryRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, ex=None):
        self.values[key] = value
        return True


def test_paper_cache_keys_include_scope_and_exact_version_without_changing_global_key():
    cache = CacheClient(MemoryRedis(), RedisSettings())
    request = AskRequest(query="question", top_k=3, model="m", use_hybrid=False)

    global_key = cache._generate_cache_key(request)
    v1_key = cache._generate_cache_key(request, paper_id="1706.03762v1")
    v7_key = cache._generate_cache_key(request, paper_id="1706.03762v7")
    assert len({global_key, v1_key, v7_key}) == 3


@pytest.mark.asyncio
async def test_scoped_cache_round_trip_does_not_leak_between_papers():
    cache = CacheClient(MemoryRedis(), RedisSettings())
    request = PaperAskRequest(query="question", top_k=2, model="m", use_hybrid=False)
    response = PaperAskResponse(
        query=request.query, answer="paper v7 answer", arxiv_id="1706.03762v7",
        source_url="https://arxiv.org/pdf/1706.03762v7", evidence=[], chunks_used=0, retrieval_mode="bm25",
    )

    assert await cache.store_paper_response(request, "1706.03762v7", response)
    assert (await cache.find_cached_paper_response(request, "1706.03762v7")).answer == "paper v7 answer"
    assert await cache.find_cached_paper_response(request, "1706.03762v1") is None
    assert await cache.find_cached_response(request) is None

