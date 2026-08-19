from types import SimpleNamespace

import pytest

from app.errors import AppError
from app.wecom.access_gate import WeComChannelAccessGate
from app.wecom.bot_bindings import WeComBotBinding


def _settings(*, environment="development", live_auth=False, access_map=None):
    return SimpleNamespace(
        app_env=environment,
        wecom_realtime_department_auth_enabled=live_auth,
        workshop_department_access_map=access_map or {"worker-1": ["焊接部"]},
        workshop_report_department="焊接部",
        wecom_corp_id="",
        wecom_corp_secret="",
        wecom_agent_id="",
        wecom_api_base_url="https://qyapi.weixin.qq.com",
        wecom_timeout_seconds=10,
    )


def _binding():
    return WeComBotBinding(
        key="welding",
        agent_id="workshop-agent",
        display_name="焊接部智能体",
        department="焊接部",
        bot_id="bot",
        secret="secret",
        ws_url="wss://example.test",
        enabled=True,
    )


def test_external_sender_is_rejected_before_department_resolution():
    gate = WeComChannelAccessGate(_settings())

    with pytest.raises(AppError, match="外部联系人") as raised:
        gate.authorize(
            {"from": {"external_userid": "external-1"}, "chatid": "chat-1"},
            binding=_binding(),
        )

    assert raised.value.code == "WECOM_CHANNEL_EXTERNAL_DENIED"


def test_missing_internal_user_id_is_rejected():
    gate = WeComChannelAccessGate(_settings())

    with pytest.raises(AppError) as raised:
        gate.authorize({"from": {}, "chatid": "chat-1"}, binding=_binding())

    assert raised.value.code == "WECOM_CHANNEL_INTERNAL_ID_REQUIRED"


def test_authorized_internal_employee_can_enter_bound_department_bot():
    gate = WeComChannelAccessGate(_settings())

    sender = gate.authorize(
        {"from": {"userid": "worker-1"}, "chatid": "chat-1"},
        binding=_binding(),
    )

    assert sender.requester_id == "worker-1"
    assert sender.chat_id == "chat-1"


def test_employee_without_bound_department_is_rejected():
    gate = WeComChannelAccessGate(
        _settings(access_map={"worker-1": ["打磨部"]})
    )

    with pytest.raises(AppError) as raised:
        gate.authorize(
            {"from": {"userid": "worker-1"}, "chatid": "chat-1"},
            binding=_binding(),
        )

    assert raised.value.code == "WORKSHOP_DEPARTMENT_FORBIDDEN"


def test_production_fails_closed_without_live_directory_authentication():
    gate = WeComChannelAccessGate(_settings(environment="production", live_auth=True))

    with pytest.raises(AppError) as raised:
        gate.authorize(
            {"from": {"userid": "worker-1"}, "chatid": "chat-1"},
            binding=_binding(),
        )

    assert raised.value.code == "WECOM_DIRECTORY_AUTH_REQUIRED"
