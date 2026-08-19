import json
import secrets
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener

from app.errors import AppError


class OpenDocScriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.source: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script" or self.source is not None:
            return
        source = dict(attrs).get("src")
        if source and "clientVarsCallback" in source:
            self.source = source


class TencentDocClient:
    def __init__(
        self,
        doc_url: str,
        sheet_id: str,
        *,
        timeout_seconds: int = 10,
        opener: Any | None = None,
    ) -> None:
        self.doc_url = doc_url
        self.sheet_id = sheet_id
        self.timeout_seconds = timeout_seconds
        self.opener = opener or build_opener(HTTPCookieProcessor(CookieJar()))

    def fetch_payload(self) -> str:
        page = self._request_text(self.doc_url)
        open_doc_url = self._extract_open_doc_url(page)
        open_doc = self._parse_jsonp(self._request_text(open_doc_url))
        client_vars = open_doc.get("clientVars")
        if not isinstance(client_vars, dict):
            raise self._invalid_data("Tencent opendoc response is missing clientVars")
        privileges = client_vars.get("privilegeAttribute")
        can_read = isinstance(privileges, dict) and privileges.get("can_read") == 1
        can_edit = isinstance(privileges, dict) and privileges.get("can_edit") in (
            0,
            False,
        )
        anonymous = client_vars.get("isLogin") is False
        if not anonymous or not can_read or not can_edit:
            raise AppError(
                "SOURCE_UNAVAILABLE",
                "Tencent document is not publicly readable",
                status_code=503,
            )
        global_pad_id = client_vars.get("globalPadId")
        if not isinstance(global_pad_id, str) or not global_pad_id:
            raise self._invalid_data("Tencent opendoc response is missing globalPadId")

        sheet_url = "https://docs.qq.com/dop-api/get/sheet?" + urlencode(
            {
                "padId": global_pad_id,
                "subId": self.sheet_id,
                "startrow": "0",
                "endrow": "200",
                "xsrf": "",
                "_r": secrets.token_hex(8),
                "outformat": "1",
                "normal": "1",
                "nowb": "1",
                "needSheetState": "1",
                "sliceStates": "1",
            }
        )
        try:
            response = json.loads(self._request_text(sheet_url))
        except json.JSONDecodeError as exc:
            raise self._invalid_data("Tencent sheet response is not JSON") from exc
        if not isinstance(response, dict) or response.get("retcode") not in (None, 0):
            raise self._invalid_data("Tencent sheet request failed")
        try:
            payload = response["data"]["initialAttributedText"]["text"][0][
                "related_sheet"
            ]
        except (IndexError, KeyError, TypeError) as exc:
            raise self._invalid_data("Tencent sheet payload is missing") from exc
        if not isinstance(payload, str) or not payload:
            raise self._invalid_data("Tencent sheet payload is empty")
        return payload

    def _request_text(self, url: str) -> str:
        request = Request(
            url,
            headers={
                "Accept": "text/html,application/json,application/javascript",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Referer": self.doc_url,
                "User-Agent": "Mozilla/5.0 TencentDocReadSync/0.1",
            },
        )
        try:
            with self.opener.open(request, timeout=self.timeout_seconds) as response:
                return response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError, OSError, UnicodeDecodeError) as exc:
            raise AppError(
                "SOURCE_UNAVAILABLE",
                "Tencent document could not be read",
                status_code=503,
            ) from exc

    def _extract_open_doc_url(self, page: str) -> str:
        parser = OpenDocScriptParser()
        parser.feed(page)
        if parser.source is None:
            raise self._invalid_data("Tencent opendoc endpoint was not found")
        open_doc_url = urljoin(self.doc_url, parser.source)
        parsed = urlsplit(open_doc_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "docs.qq.com"
            or parsed.path != "/dop-api/opendoc"
        ):
            raise self._invalid_data("Tencent opendoc endpoint is not trusted")
        return open_doc_url

    @staticmethod
    def _parse_jsonp(payload: str) -> dict:
        prefix = "clientVarsCallback("
        stripped = payload.strip()
        if not stripped.startswith(prefix):
            raise TencentDocClient._invalid_data("Tencent opendoc response is not JSONP")
        suffix = stripped[len(prefix) :]
        if suffix.endswith(";"):
            suffix = suffix[:-1].rstrip()
        if not suffix.endswith(")"):
            raise TencentDocClient._invalid_data("Tencent opendoc response is incomplete")
        try:
            result = json.loads(suffix[:-1])
        except json.JSONDecodeError as exc:
            raise TencentDocClient._invalid_data(
                "Tencent opendoc response is invalid"
            ) from exc
        if not isinstance(result, dict):
            raise TencentDocClient._invalid_data("Tencent opendoc response is invalid")
        return result

    @staticmethod
    def _invalid_data(message: str) -> AppError:
        return AppError("INVALID_SOURCE_DATA", message, status_code=422)
