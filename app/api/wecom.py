import secrets

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field

from app.api.dependencies import verify_business_api_key
from app.config import Settings, get_settings
from app.errors import AppError
from app.wecom.access_gate import WeComChannelAccessGate
from app.wecom.agent_bridge import WeComAgentBridge
from app.wecom.bot_bindings import build_wecom_bot_bindings


router = APIRouter(prefix="/wecom", tags=["wecom"])


class DepartmentBotStatus(BaseModel):
    key: str
    display_name: str
    department: str
    configured: bool
    enabled: bool
    started: bool
    connected: bool
    authenticated: bool
    last_error_code: str | None = None


class WeComStatus(BaseModel):
    configured: bool
    started: bool
    connected: bool
    authenticated: bool
    last_error_code: str | None = None
    callback_configured: bool
    agent_mode: str
    agent_configured: bool
    default_agent_id: str = "workshop-agent"
    bots: list[DepartmentBotStatus] = Field(default_factory=list)


class WeComInboundMessage(BaseModel):
    message_id: str = Field(min_length=1, max_length=255)
    user_id: str = Field(min_length=1, max_length=200)
    chat_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=12000)
    bot_key: str = Field(default="packaging", pattern=r"^[a-z][a-z0-9_-]{1,39}$")


class WeComPushRequest(BaseModel):
    bot_key: str = Field(default="packaging", pattern=r"^[a-z][a-z0-9_-]{1,39}$")
    recipient_id: str | None = Field(default=None, min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=12000)


class WeComPushResponse(BaseModel):
    status: str
    message_id: str


class WeComAgentMessageResponse(BaseModel):
    request_id: str
    status: str
    message: str


def verify_wecom_callback_token(
    token: str | None = Header(default=None, alias="X-WeCom-Token"),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.wecom_callback_token:
        raise AppError("WECOM_CALLBACK_NOT_CONFIGURED", "企业微信回调密钥尚未配置", status_code=503)
    if token is None or not secrets.compare_digest(token, settings.wecom_callback_token):
        raise AppError("UNAUTHORIZED", "企业微信回调鉴权失败", status_code=401)


def verify_wecom_connection_api_key(
    api_key: str | None = Header(default=None, alias="X-WeCom-Key"),
    settings: Settings = Depends(get_settings),
) -> None:
    """Second factor for operator-facing WeCom endpoints."""
    if not settings.wecom_connection_api_key:
        raise AppError(
            "WECOM_CONNECTION_KEY_NOT_CONFIGURED",
            "企业微信连接层 API 密钥尚未配置",
            status_code=503,
        )
    if api_key is None or not secrets.compare_digest(api_key, settings.wecom_connection_api_key):
        raise AppError("UNAUTHORIZED", "企业微信连接层鉴权失败", status_code=401)


@router.get(
    "/status", response_model=WeComStatus,
    dependencies=[Depends(verify_business_api_key), Depends(verify_wecom_connection_api_key)],
)
def get_wecom_status(request: Request, settings: Settings = Depends(get_settings)) -> WeComStatus:
    runner = getattr(request.app.state, "wecom_aibot_runner", None)
    runners = getattr(request.app.state, "wecom_aibot_runners", {})
    bindings = build_wecom_bot_bindings(settings)
    agent_bridge = WeComAgentBridge(settings)
    return WeComStatus(
        configured=bool(settings.wecom_aibot_bot_id and settings.wecom_aibot_secret),
        started=bool(runner and runner.client is not None),
        connected=bool(runner and runner.is_connected),
        authenticated=bool(runner and runner.is_authenticated),
        last_error_code=runner.last_error_code if runner else "WECOM_AIBOT_NOT_STARTED",
        callback_configured=False,
        agent_mode=agent_bridge.mode,
        agent_configured=agent_bridge.is_configured,
        bots=[
            DepartmentBotStatus(
                key=binding.key,
                display_name=binding.display_name,
                department=binding.department,
                configured=binding.configured,
                enabled=binding.enabled,
                started=bool(runners.get(binding.key) and runners[binding.key].client is not None),
                connected=bool(runners.get(binding.key) and runners[binding.key].is_connected),
                authenticated=bool(runners.get(binding.key) and runners[binding.key].is_authenticated),
                last_error_code=(runners[binding.key].last_error_code if runners.get(binding.key) else None),
            )
            for binding in bindings
        ],
    )


@router.post(
    "/messages", response_model=WeComAgentMessageResponse,
    dependencies=[Depends(verify_wecom_callback_token)],
)
def receive_wecom_message(
    payload: WeComInboundMessage,
    settings: Settings = Depends(get_settings),
) -> WeComAgentMessageResponse:
    bindings = {binding.key: binding for binding in build_wecom_bot_bindings(settings)}
    binding = bindings.get(payload.bot_key)
    if binding is None or not binding.enabled or not binding.configured:
        raise AppError(
            "WECOM_BOT_UNAVAILABLE",
            "企业微信机器人不可用",
            status_code=503,
        )
    sender = WeComChannelAccessGate(settings).authorize(
        {"from": {"userid": payload.user_id}, "chatid": payload.chat_id},
        binding=binding,
    )
    response = WeComAgentBridge(settings).invoke(
        binding=binding,
        requester_id=sender.requester_id,
        chat_id=sender.chat_id,
        message_id=payload.message_id,
        text=payload.text,
    )
    return WeComAgentMessageResponse(**response.__dict__)


@router.post(
    "/push", response_model=WeComPushResponse,
    dependencies=[Depends(verify_business_api_key), Depends(verify_wecom_connection_api_key)],
)
async def push_wecom_message(
    payload: WeComPushRequest,
    request: Request,
) -> WeComPushResponse:
    runners = getattr(request.app.state, "wecom_aibot_runners", {})
    runner = runners.get(payload.bot_key)
    if runner is None and payload.bot_key == "packaging":
        runner = getattr(request.app.state, "wecom_aibot_runner", None)
    if runner is None:
        raise AppError("WECOM_AIBOT_NOT_STARTED", "企业微信 AIBot 长连接尚未启动", status_code=503)
    chat_id = payload.recipient_id or runner.last_chat_id
    if not chat_id:
        raise AppError(
            "WECOM_AIBOT_CHAT_UNKNOWN",
            "尚未收到群消息，无法确定主动推送目标会话",
            status_code=409,
        )
    message_id = await runner.send_text(chat_id, payload.text)
    return WeComPushResponse(status="sent", message_id=message_id)
