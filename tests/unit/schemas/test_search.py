import pytest
from pydantic import ValidationError
from src.schema.api.search import SearchHit, SearchRequest,  SearchResponse 

def test_search_request_valid():
    """Test valid SearchRequest creation."""
    request = SearchRequest(query = "neural_networks", size = 10, latest_papers = True , categories = ["cs.AI", "cs.LG"])
    assert request.query == "neural_networks"
    assert request.size == 10
    assert request.from_ == 0 # default value
    assert request.latest_papers is True
    assert request.categories == ["cs.AI", "cs.LG"]
