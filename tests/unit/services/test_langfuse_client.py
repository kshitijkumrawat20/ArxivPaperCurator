from types import SimpleNamespace

import pytest

from src.services.langfuse.client import LangfuseTracer


class _Observation:
    def __enter__(self):
        return SimpleNamespace(update=lambda **kwargs: None)

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class _Client:
    def start_as_current_observation(self, **kwargs):
        return _Observation()


@pytest.mark.parametrize("error", [ValueError("generation failed"), RuntimeError("request failed")])
def test_trace_rag_request_propagates_request_errors(error: Exception) -> None:
    tracer = object.__new__(LangfuseTracer)
    tracer.client = _Client()

    with pytest.raises(type(error), match=str(error)):
        with tracer.trace_rag_request("question", user_id="api_user"):
            raise error
