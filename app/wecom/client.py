import time

import httpx

from app.config import Settings
from app.errors import AppError


class WeComClient:
    """Small, secret-safe client for Enterprise WeChat application messages."""

    def __init__(self, settings: Settings) -> None:
        self.corp_id = getattr(settings, "wecom_corp_id", "")
        self.corp_secret = getattr(settings, "wecom_corp_secret", "")
        self.agent_id = getattr(settings, "wecom_agent_id", "")
        self.base_url = getattr(
            settings, "wecom_api_base_url", "https://qyapi.weixin.qq.com"
        ).rstrip("/")
        self.timeout_seconds = getattr(settings, "wecom_timeout_seconds", 10)
        self._access_token = ""
        self._token_expires_at = 0.0

    @property
    def is_configured(self) -> bool:
        return bool(self.corp_id and self.corp_secret and self.agent_id)

    def send_text(self, recipient_id: str, text: str) -> str:
        if not self.is_configured:
            raise AppError("WECOM_NOT_CONFIGURED", "企业微信应用尚未配置", status_code=503)
        response = httpx.post(
            f"{self.base_url}/cgi-bin/message/send",
            params={"access_token": self._get_access_token()},
            json={
                "touser": recipient_id,
                "msgtype": "text",
                "agentid": int(self.agent_id),
                "text": {"content": text},
                "safe": 0,
            },
            timeout=self.timeout_seconds,
            trust_env=False,
        )
        payload = self._verify(response, "企业微信消息发送失败")
        return str(payload.get("msgid") or "")

    def get_user_departments(self, user_id: str) -> frozenset[str]:
        """Read the employee's current department membership from WeCom.

        The employee record is deliberately fetched on every authorization;
        only the short-lived access token is cached.
        """
        if not self.is_configured:
            raise AppError("WECOM_NOT_CONFIGURED", "企业微信通讯录应用尚未配置", status_code=503)
        token = self._get_access_token()
        user_response = httpx.get(
            f"{self.base_url}/cgi-bin/user/get",
            params={"access_token": token, "userid": user_id},
            timeout=self.timeout_seconds, trust_env=False,
        )
        user = self._verify(user_response, "无法实时读取企业微信员工部门")
        department_ids = {str(item) for item in (user.get("department") or [])}
        if not department_ids:
            raise AppError("WECOM_DEPARTMENT_EMPTY", "当前员工未归属任何企业微信部门", status_code=403)
        directory_response = httpx.get(
            f"{self.base_url}/cgi-bin/department/simplelist",
            params={"access_token": token},
            timeout=self.timeout_seconds, trust_env=False,
        )
        directory = self._verify(directory_response, "无法实时读取企业微信部门目录")
        rows = directory.get("department_id") or directory.get("department") or []
        id_to_name = {str(row.get("id")): str(row.get("name") or "").strip() for row in rows}
        names = frozenset(id_to_name[item] for item in department_ids if id_to_name.get(item))
        if not names:
            raise AppError("WECOM_DEPARTMENT_UNRESOLVED", "员工部门无法映射到部门名称", status_code=502)
        return names

    def _get_access_token(self) -> str:
        if self._access_token and time.monotonic() < self._token_expires_at:
            return self._access_token
        response = httpx.get(
            f"{self.base_url}/cgi-bin/gettoken",
            params={"corpid": self.corp_id, "corpsecret": self.corp_secret},
            timeout=self.timeout_seconds,
            trust_env=False,
        )
        payload = self._verify(response, "企业微信应用鉴权失败")
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise AppError("WECOM_AUTH_FAILED", "企业微信应用鉴权失败", status_code=502)
        self._access_token = token
        self._token_expires_at = time.monotonic() + max(int(payload.get("expires_in") or 7200) - 300, 60)
        return token

    @staticmethod
    def _verify(response: httpx.Response, message: str) -> dict:
        try:
            payload = response.json()
        except ValueError as exc:
            raise AppError("WECOM_REQUEST_FAILED", message, status_code=502) from exc
        if response.status_code >= 400 or payload.get("errcode") != 0:
            raise AppError(
                "WECOM_REQUEST_FAILED", message, status_code=502,
                details={"http_status": response.status_code, "errcode": payload.get("errcode")},
            )
        return payload
