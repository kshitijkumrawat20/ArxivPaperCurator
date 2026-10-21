from src.main import app


def test_paper_list_and_detail_routes_are_registered():
    registered_routes = {route.path for route in app.routes}

    assert "/api/v1/papers/" in registered_routes
    assert "/api/v1/papers/discover" in registered_routes
    assert "/api/v1/papers/{arxiv_id}" in registered_routes
