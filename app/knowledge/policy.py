from dataclasses import dataclass

from app.errors import AppError
from app.knowledge.contracts import KnowledgeDomain


@dataclass(frozen=True)
class AgentKnowledgePolicy:
    private_domain: KnowledgeDomain
    allowed_domains: frozenset[KnowledgeDomain]


def resolve_allowed_domains(
    agent_id: str,
    requested_domains: list[KnowledgeDomain] | None,
) -> list[KnowledgeDomain]:
    # Local import prevents a policy/agent manifest import cycle.
    from app.agents.registry import AGENT_KNOWLEDGE_POLICIES

    policy = AGENT_KNOWLEDGE_POLICIES.get(agent_id)
    if policy is None:
        raise AppError(
            "KNOWLEDGE_POLICY_NOT_CONFIGURED",
            "该智能体尚未配置知识域访问策略",
            status_code=403,
            details={"agent_id": agent_id},
        )
    effective = set(requested_domains or policy.allowed_domains)
    forbidden = effective - policy.allowed_domains
    if forbidden:
        raise AppError(
            "KNOWLEDGE_DOMAIN_ACCESS_DENIED",
            "智能体无权访问请求的知识域",
            status_code=403,
            details={"agent_id": agent_id, "forbidden_domains": sorted(forbidden)},
        )
    return sorted(effective)
