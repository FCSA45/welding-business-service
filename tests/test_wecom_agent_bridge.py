from types import SimpleNamespace

from app.wecom.agent_bridge import WeComAgentBridge
from app.wecom.bot_bindings import WeComBotBinding


def _binding() -> WeComBotBinding:
    return WeComBotBinding(
        key="welding",
        agent_id="workshop-agent",
        display_name="Welding agent",
        department="Welding",
        bot_id="bot-id",
        secret="bot-secret",
        ws_url="wss://example.test",
        enabled=True,
    )


def _settings(**overrides):
    values = {
        "wecom_agent_mode": "cherry_local",
        "cherry_agent_api_url": "http://127.0.0.1:24333",
        "cherry_agent_api_key": "key",
        "cherry_agent_id": "agent-1",
        "cherry_agent_timeout_seconds": 10,
        "cherry_agent_default_session_id": "",
        "hermes_agent_url": "",
        "hermes_agent_api_key": "",
        "hermes_agent_timeout_seconds": 10,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_cherry_sse_response_is_forwarded(monkeypatch):
    class FakeResponse:
        text = (
            'data: {"type":"text-delta","text":"中间内容"}\n'
            'data: {"type":"finish","raw":{"result":"Cherry 已返回"}}\n'
            "data: [DONE]\n"
        )

        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "session-1"}

    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append((url, json))
        return FakeResponse()

    monkeypatch.setattr("app.wecom.agent_bridge.httpx.post", fake_post)
    monkeypatch.setattr("app.wecom.agent_bridge.httpx.get", lambda *args, **kwargs: FakeResponse({"data": []}))
    response = WeComAgentBridge(_settings()).invoke(
        binding=_binding(), requester_id="user-1", chat_id="chat-1",
        message_id="msg-1", text="hello",
    )

    assert response.message == "Cherry 已返回"
    assert calls[0][0].endswith("/v1/agents/agent-1/sessions")
    assert calls[1][0].endswith("/v1/agents/agent-1/sessions/session-1/messages")


def test_cherry_session_is_reused(monkeypatch):
    class FakeResponse:
        def __init__(self, json_body=None):
            self._json_body = json_body
            self.text = 'data: {"type":"finish","raw":{"result":"ok"}}'

        def raise_for_status(self):
            return None

        def json(self):
            return self._json_body

    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append(url)
        return FakeResponse({"id": "session-1"} if url.endswith("/sessions") else None)

    monkeypatch.setattr("app.wecom.agent_bridge.httpx.post", fake_post)
    monkeypatch.setattr("app.wecom.agent_bridge.httpx.get", lambda *args, **kwargs: FakeResponse({"data": []}))
    bridge = WeComAgentBridge(_settings())
    for index in range(2):
        bridge.invoke(
            binding=_binding(), requester_id="user-1", chat_id="chat-1",
            message_id=f"msg-{index}", text="hello",
        )

    assert calls == [
        "http://127.0.0.1:24333/v1/agents/agent-1/sessions",
        "http://127.0.0.1:24333/v1/agents/agent-1/sessions/session-1/messages",
        "http://127.0.0.1:24333/v1/agents/agent-1/sessions/session-1/messages",
    ]


def test_hermes_bridge_returns_external_agent_message(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"request_id": "hermes-1", "status": "ok", "message": "done"}

    def fake_post(url, *, json, headers, timeout):
        captured.update(url=url, json=json, headers=headers, timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr("app.wecom.agent_bridge.httpx.post", fake_post)
    bridge = WeComAgentBridge(_settings(
        wecom_agent_mode="hermes",
        hermes_agent_url="https://hermes.example.test/agent/invoke",
        hermes_agent_api_key="secret",
    ))
    response = bridge.invoke(
        binding=_binding(), requester_id="user-1", chat_id="chat-1",
        message_id="msg-1", text="查询昨日订单日报",
    )

    assert response.message == "done"
    assert response.request_id == "hermes-1"
    assert captured["json"]["agent_id"] == "workshop-agent"
    assert captured["json"]["department"] == "Welding"
    assert captured["headers"]["Authorization"] == "Bearer secret"
