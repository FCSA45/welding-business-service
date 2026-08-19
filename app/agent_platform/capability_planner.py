"""Model-planned capability selection with server-enforced execution boundaries."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re

from app.ai.gateway import ModelGateway
from app.errors import AppError


CAPABILITY_CATALOG = (
    ("direct_response", "Natural conversation or a question answerable without enterprise evidence", False),
    ("enterprise_knowledge", "A question that requires authorized department rules or knowledge", True),
    ("business_guidance", "Business troubleshooting that requires authorized department context", True),
    ("read_only_data_guidance", "Explain which approved read-only report/query capability should be used", True),
    ("refuse_write_action", "A request to modify, delete, create, or disclose protected enterprise data", False),
)


@dataclass(frozen=True)
class CapabilityPlan:
    capability: str
    requires_retrieval: bool
    answer: str = ""
    confidence: float = 0.0
    model: str = ""
    duration_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


class AgentCapabilityPlanner:
    def __init__(self, gateway: ModelGateway) -> None:
        self.gateway = gateway

    def plan(
        self, *, message: str, agent_name: str, department: str = "",
        conversation_context: str = "",
    ) -> CapabilityPlan:
        catalog = "\n".join(
            f"- {name}: {description}; retrieval={str(retrieval).lower()}"
            for name, description, retrieval in CAPABILITY_CATALOG
        )
        completion = self.gateway.complete_with_metadata(
            system_prompt=(
                "You are an enterprise agent capability planner. Select exactly one capability from the catalog. "
                "Do not invent data or grant permissions. Department and read-only boundaries are immutable. "
                "For direct_response or refuse_write_action, provide the final concise Chinese answer. "
                "For retrieval capabilities, leave answer empty. Return JSON only with keys: "
                "capability, confidence, answer.\n\nCapability catalog:\n" + catalog
            ),
            user_prompt=(
                f"Agent: {agent_name}\nBound department: {department or 'not specified'}\n"
                f"Recent conversation:\n{conversation_context or '-'}\n\nUser message:\n{message}"
            ),
            temperature=0,
        )
        values = self._parse_json(completion.content)
        allowed = {name: retrieval for name, _description, retrieval in CAPABILITY_CATALOG}
        capability = str(values.get("capability") or "").strip()
        if capability not in allowed:
            raise AppError("CAPABILITY_PLAN_INVALID", "智能体能力计划无效", status_code=502)
        answer = str(values.get("answer") or "").strip()
        requires_retrieval = allowed[capability]
        if not requires_retrieval and not answer:
            raise AppError("CAPABILITY_PLAN_EMPTY_ANSWER", "智能体计划缺少回答", status_code=502)
        try:
            confidence = max(0.0, min(1.0, float(values.get("confidence") or 0)))
        except (TypeError, ValueError):
            confidence = 0.0
        return CapabilityPlan(
            capability=capability, requires_retrieval=requires_retrieval,
            answer=answer, confidence=confidence, model=completion.model,
            duration_ms=completion.duration_ms, prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
        )

    @staticmethod
    def _parse_json(content: str) -> dict:
        cleaned = content.strip()
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            cleaned = fenced.group(1)
        try:
            values = json.loads(cleaned)
        except (json.JSONDecodeError, TypeError) as exc:
            raise AppError("CAPABILITY_PLAN_INVALID_JSON", "智能体能力计划格式无效", status_code=502) from exc
        if not isinstance(values, dict):
            raise AppError("CAPABILITY_PLAN_INVALID_JSON", "智能体能力计划格式无效", status_code=502)
        return values
