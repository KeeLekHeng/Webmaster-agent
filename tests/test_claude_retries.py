import httpx
import pytest

from guardian.investigation import ClaudeInvestigator


def setup_client(monkeypatch, outcomes):
    calls, waits = [], []
    real_client = httpx.Client
    def handler(request):
        calls.append(request)
        outcome = outcomes.pop(0)
        if outcome == "timeout":
            raise httpx.ReadTimeout("synthetic timeout", request=request)
        if outcome == "connection":
            raise httpx.ConnectError("synthetic connection failure", request=request)
        if outcome != 200:
            return httpx.Response(outcome, json={"error": {"type": "api_error", "message": "synthetic"}})
        return httpx.Response(200, json={"id": "msg_test", "type": "message", "role": "assistant",
            "model": "test-model", "content": [{"type": "text", "text": '{"priorities":[]}'}],
            "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 10}})
    class MockClient(real_client):
        def __init__(self, **kw):
            super().__init__(**kw, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, "Client", MockClient)
    monkeypatch.setattr("guardian.investigation.retry_wait", waits.append)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-test-key")
    return ClaudeInvestigator("test-model"), calls, waits


def test_three_retries_then_success(monkeypatch):
    client, calls, waits = setup_client(monkeypatch, ["timeout", 429, 503, 200])
    assert client({}).priorities == []
    assert waits == [2, 4, 8]
    assert len(calls) == 4
    assert client.usage["request_attempts"] == 4


def test_stop_after_three_retries(monkeypatch):
    import anthropic
    client, calls, waits = setup_client(monkeypatch, [503] * 4)
    with pytest.raises(anthropic.APIStatusError):
        client({})
    assert len(calls) == 4
    assert waits == [2, 4, 8]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_permanent_error_has_no_retry(monkeypatch, status):
    import anthropic
    client, calls, waits = setup_client(monkeypatch, [status])
    with pytest.raises(anthropic.APIStatusError):
        client({})
    assert len(calls) == 1
    assert waits == []


@pytest.mark.parametrize("failure", ["connection", 408, 409, 429, 500, 529])
def test_transient_errors_retry(monkeypatch, failure):
    client, calls, waits = setup_client(monkeypatch, [failure, 200])
    client({})
    assert len(calls) == 2
    assert waits == [2]


def test_kill_switch_blocks_retry(monkeypatch):
    from guardian.network import PolicyError
    client, calls, waits = setup_client(monkeypatch, [503, 200])
    def stop(seconds):
        monkeypatch.setenv("AGENT_ENABLED", "false")
    monkeypatch.setattr("guardian.investigation.retry_wait", stop)
    with pytest.raises(PolicyError):
        client({})
    assert len(calls) == 1


def test_kill_switch_checked_during_backoff(monkeypatch):
    from guardian.investigation import retry_wait
    from guardian.network import PolicyError
    def stop(seconds):
        monkeypatch.setenv("AGENT_ENABLED", "false")
    monkeypatch.setattr("guardian.investigation.time.sleep", stop)
    with pytest.raises(PolicyError):
        retry_wait(8)
