import pytest
from pydantic import BaseModel, ValidationError

from warden import llm as llm_module
from warden.llm import FallbackStructured


class SampleAction(BaseModel):
    action: str
    message: str


class FakeResponse:
    def __init__(self, content):
        self.content = content


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def ainvoke(self, messages, **kwargs):
        self.calls += 1
        if not self.responses:
            raise AssertionError("FakeLLM exhausted responses (unexpected extra call)")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)


@pytest.fixture(autouse=True)
def no_retry_backoff(monkeypatch):
    """Default tests to single-attempt mode; retry-specific tests override this."""
    monkeypatch.setattr(llm_module, "RETRY_ATTEMPTS", 1)


async def test_invalid_json_falls_back_to_next_provider():
    broken = FakeLLM(["I cannot answer in JSON."])
    healthy = FakeLLM(['{"action": "accept", "message": "Deal"}'])
    result = await FallbackStructured([broken, healthy], SampleAction).ainvoke([])

    assert result == SampleAction(action="accept", message="Deal")
    assert broken.calls == 1
    assert healthy.calls == 1


async def test_rate_limit_falls_back_to_next_provider():
    rate_limited = FakeLLM([RuntimeError("429 rate limit exceeded")])
    healthy = FakeLLM(['{"action": "counter", "message": "Rs.2500"}'])
    result = await FallbackStructured([rate_limited, healthy], SampleAction).ainvoke([])

    assert result.action == "counter"
    assert rate_limited.calls == 1
    assert healthy.calls == 1


async def test_all_invalid_outputs_raise():
    providers = [
        FakeLLM(["not json"]),
        FakeLLM(['{"action": "accept"}']),
    ]
    with pytest.raises(ValidationError):
        await FallbackStructured(providers, SampleAction).ainvoke([])


async def test_exhausted_quota_falls_back_to_next_provider():
    quota_exhausted = FakeLLM([RuntimeError("Error code: 403 - insufficient_user_quota; credit limit is insufficient")])
    healthy = FakeLLM(['{"action": "reject", "message": "No deal"}'])
    result = await FallbackStructured([quota_exhausted, healthy], SampleAction).ainvoke([])

    assert result.action == "reject"
    assert quota_exhausted.calls == 1
    assert healthy.calls == 1


class TestSameProviderRetry:
    """TokenRouter capacity blips (503 server_selection_failed) are transient;
    the provider should be retried before burning the next tier's quota."""

    async def test_transient_503_retried_then_succeeds(self, monkeypatch):
        monkeypatch.setattr(llm_module, "RETRY_ATTEMPTS", 3)
        monkeypatch.setattr(llm_module, "RETRY_BACKOFF_SECONDS", (0.0, 0.0))
        flaky = FakeLLM(
            [
                RuntimeError("503 No available servers: Policy cache_aware failed to select a prefill worker"),
                RuntimeError("503 Service Unavailable"),
                '{"action": "accept", "message": "ok"}',
            ]
        )
        never_called = FakeLLM([])
        result = await FallbackStructured([flaky, never_called], SampleAction).ainvoke([])

        assert result.action == "accept"
        assert flaky.calls == 3
        assert never_called.calls == 0

    async def test_persistent_failure_exhausts_retries_then_falls_through(self, monkeypatch):
        monkeypatch.setattr(llm_module, "RETRY_ATTEMPTS", 3)
        monkeypatch.setattr(llm_module, "RETRY_BACKOFF_SECONDS", (0.0, 0.0))
        dead = FakeLLM([RuntimeError("503 service unavailable")] * 3)
        healthy = FakeLLM(['{"action": "reject", "message": "moved on"}'])
        result = await FallbackStructured([dead, healthy], SampleAction).ainvoke([])

        assert result.action == "reject"
        assert dead.calls == 3
        assert healthy.calls == 1

    async def test_non_retryable_error_raises_immediately(self, monkeypatch):
        monkeypatch.setattr(llm_module, "RETRY_ATTEMPTS", 3)
        fatal = FakeLLM([RuntimeError("authentication failed: bad api key shape")])
        never_called = FakeLLM([])
        with pytest.raises(RuntimeError, match="bad api key shape"):
            await FallbackStructured([fatal, never_called], SampleAction).ainvoke([])
        assert fatal.calls == 1
        assert never_called.calls == 0


class TestExtractJsonRobustness:
    def test_list_of_content_parts_is_joined(self):
        content = [
            {"type": "text", "text": 'Here you go: {"action": '},
            {"type": "text", "text": '"accept", "message": "hi"}'},
        ]
        parsed = FallbackStructured._extract_json(content)
        assert parsed == {"action": "accept", "message": "hi"}

    def test_plain_reasoning_prefix_is_skipped(self):
        parsed = FallbackStructured._extract_json('\n\n{"reply": "ok"}')
        assert parsed == {"reply": "ok"}

    def test_none_content_raises_value_error(self):
        with pytest.raises(ValueError, match="not text"):
            FallbackStructured._extract_json(None)
