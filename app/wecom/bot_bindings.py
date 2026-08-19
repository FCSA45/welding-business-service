"""Secret-safe configuration for department-bound WeCom AIBots."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings


@dataclass(frozen=True)
class WeComBotBinding:
    key: str
    agent_id: str
    display_name: str
    department: str
    bot_id: str
    secret: str
    ws_url: str
    enabled: bool
    cherry_agent_id: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.bot_id and self.secret)


def build_wecom_bot_bindings(settings: Settings) -> tuple[WeComBotBinding, ...]:
    return (
        WeComBotBinding(
            key="packaging",
            agent_id="workshop-agent",
            cherry_agent_id=getattr(settings, "cherry_agent_id", ""),
            display_name="焊接部报表机器人",
            department=getattr(settings, "workshop_report_department", "焊接部"),
            bot_id=getattr(settings, "wecom_aibot_bot_id", ""),
            secret=getattr(settings, "wecom_aibot_secret", ""),
            ws_url=getattr(settings, "wecom_aibot_ws_url", "wss://openws.work.weixin.qq.com"),
            enabled=getattr(settings, "wecom_aibot_enabled", True),
        ),
        WeComBotBinding(
            key="grinding",
            agent_id="workshop-agent",
            cherry_agent_id=getattr(settings, "cherry_agent_id", ""),
            display_name="打磨部报表机器人",
            department="打磨部",
            bot_id=getattr(settings, "grinding_wecom_aibot_bot_id", ""),
            secret=getattr(settings, "grinding_wecom_aibot_secret", ""),
            ws_url=getattr(settings, "grinding_wecom_aibot_ws_url", "wss://openws.work.weixin.qq.com"),
            enabled=getattr(settings, "grinding_wecom_aibot_enabled", False),
        ),
        WeComBotBinding(
            key="welding",
            agent_id="workshop-agent",
            cherry_agent_id=getattr(settings, "cherry_agent_id", ""),
            display_name="焊接部智能体",
            department="焊接部",
            bot_id=getattr(settings, "welding_wecom_aibot_bot_id", ""),
            secret=getattr(settings, "welding_wecom_aibot_secret", ""),
            ws_url=getattr(settings, "welding_wecom_aibot_ws_url", "wss://openws.work.weixin.qq.com"),
            enabled=getattr(settings, "welding_wecom_aibot_enabled", False),
        ),
        WeComBotBinding(
            key="engraving",
            agent_id="workshop-agent",
            cherry_agent_id=getattr(settings, "cherry_agent_id", ""),
            display_name="雕刻部智能体",
            department="雕刻部",
            bot_id=getattr(settings, "engraving_wecom_aibot_bot_id", ""),
            secret=getattr(settings, "engraving_wecom_aibot_secret", ""),
            ws_url=getattr(settings, "engraving_wecom_aibot_ws_url", "wss://openws.work.weixin.qq.com"),
            enabled=getattr(settings, "engraving_wecom_aibot_enabled", False),
        ),
        WeComBotBinding(
            key="painting",
            agent_id="painting-agent",
            cherry_agent_id=getattr(settings, "painting_cherry_agent_id", ""),
            display_name="油漆部智能体",
            department="油漆部",
            bot_id=getattr(settings, "painting_wecom_aibot_bot_id", ""),
            secret=getattr(settings, "painting_wecom_aibot_secret", ""),
            ws_url=getattr(settings, "painting_wecom_aibot_ws_url", "wss://openws.work.weixin.qq.com"),
            enabled=getattr(settings, "painting_wecom_aibot_enabled", False),
        ),
    )
