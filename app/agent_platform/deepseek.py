import json
import logging
from dataclasses import dataclass

import httpx

from app.agent_platform.search import QueryPlan, build_query_plan, normalize_text, tokenize
from app.config import Settings


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeepSeekQueryEnhancer:
    """Optional Chinese query rewriting; local retrieval remains the source of truth."""

    api_key: str
    base_url: str
    model: str
    timeout_seconds: int

    @classmethod
    def from_settings(cls, settings: Settings) -> "DeepSeekQueryEnhancer | None":
        if not settings.deepseek_api_key:
            return None
        return cls(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url.rstrip("/"),
            model=settings.deepseek_model,
            timeout_seconds=settings.deepseek_timeout_seconds,
        )

    def enhance(self, query: str, fallback: QueryPlan) -> QueryPlan:
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "你是广告牌标识公司知识库检索预处理器。只做意图识别和查询改写，"
                                "不要回答问题。返回 JSON：intent、rewritten_queries、terms。"
                                "intent 只能是 report_generation、rule_lookup、data_status、"
                                "troubleshooting、action_request、general_question。"
                            ),
                        },
                        {"role": "user", "content": query},
                    ],
                },
                timeout=self.timeout_seconds,
                trust_env=False,
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            intent = str(parsed.get("intent") or fallback.intent)
            allowed = {"report_generation", "rule_lookup", "data_status", "troubleshooting", "action_request", "general_question"}
            if intent not in allowed:
                intent = fallback.intent
            rewrites = [str(item).strip() for item in parsed.get("rewritten_queries", []) if str(item).strip()]
            rewrites = list(dict.fromkeys([query.strip(), *rewrites, *fallback.rewritten_queries]))
            terms = {str(item).strip().lower() for item in parsed.get("terms", []) if str(item).strip()}
            terms.update(tokenize(" ".join(rewrites)))
            return QueryPlan(query, intent, rewrites, terms, fallback.filters)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
            logger.warning("DeepSeek query enhancement failed; using local query plan", exc_info=True)
            return fallback
