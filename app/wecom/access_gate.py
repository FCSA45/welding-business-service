"""Fail-closed admission control for inbound WeCom AIBot messages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.errors import AppError
from app.wecom.bot_bindings import WeComBotBinding
from app.workshop.access import resolve_department_scope


EXTERNAL_ID_FIELDS = (
    "external_userid",
    "external_user_id",
    "external_contact_id",
)
EXTERNAL_TYPE_VALUES = {
    "external",
    "external_user",
    "external_contact",
    "customer",
}


@dataclass(frozen=True)
class AuthorizedWeComSender:
    requester_id: str
    chat_id: str


class WeComChannelAccessGate:
    """Authorize a sender before conversation, model, or business handling."""

    def __init__(self, settings) -> None:
        self.settings = settings

    def authorize(self, body: dict[str, Any], *, binding: WeComBotBinding) -> AuthorizedWeComSender:
        sender = body.get("from")
        if not isinstance(sender, dict):
            raise AppError(
                "WECOM_CHANNEL_SENDER_INVALID",
                "企业微信消息缺少有效发送者身份",
                status_code=403,
            )
        if self._is_external_sender(body, sender):
            raise AppError(
                "WECOM_CHANNEL_EXTERNAL_DENIED",
                "外部联系人无权使用内部业务机器人",
                status_code=403,
            )

        requester_id = self._internal_user_id(sender)
        if not requester_id:
            raise AppError(
                "WECOM_CHANNEL_INTERNAL_ID_REQUIRED",
                "仅支持已验证的企业内部员工使用该机器人",
                status_code=403,
            )
        chat_id = str(body.get("chatid") or requester_id).strip()
        if not chat_id:
            raise AppError(
                "WECOM_CHANNEL_CHAT_REQUIRED",
                "企业微信消息缺少会话身份",
                status_code=403,
            )

        scope = resolve_department_scope(
            self.settings, requester_id, chat_id=chat_id
        )
        scope.require(binding.department)
        return AuthorizedWeComSender(requester_id=requester_id, chat_id=chat_id)

    @staticmethod
    def _internal_user_id(sender: dict[str, Any]) -> str:
        return str(sender.get("userid") or sender.get("user_id") or "").strip()

    @staticmethod
    def _is_external_sender(body: dict[str, Any], sender: dict[str, Any]) -> bool:
        for field in EXTERNAL_ID_FIELDS:
            if sender.get(field) or body.get(field):
                return True
        if sender.get("is_external") is True or sender.get("external") is True:
            return True
        sender_type = str(sender.get("type") or sender.get("user_type") or "").strip().lower()
        return sender_type in EXTERNAL_TYPE_VALUES
