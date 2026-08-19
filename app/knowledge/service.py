from typing import Protocol

from app.knowledge.contracts import (
    KnowledgeDomain,
    KnowledgeSearchHit,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
)
from app.knowledge.policy import resolve_allowed_domains
from app.knowledge.guardrails import inspect_query, should_answer
from app.errors import AppError


class KnowledgeSearcher(Protocol):
    def search(
        self,
        agent_id: str,
        query: str,
        limit: int = 5,
        domains: list[KnowledgeDomain] | None = None,
    ) -> list: ...


class KnowledgeService:
    """Stable boundary used by agents, independent of database/vector backend."""

    def __init__(self, searcher: KnowledgeSearcher) -> None:
        self.searcher = searcher

    def search(self, request: KnowledgeSearchRequest) -> KnowledgeSearchResponse:
        safety = inspect_query(request.query)
        if not safety.allowed:
            raise AppError(
                "UNSAFE_KNOWLEDGE_QUERY",
                "查询包含绕过权限或获取敏感信息的指令",
                status_code=400,
                details={"reason": safety.reason},
            )
        domains = resolve_allowed_domains(request.agent_id, request.domains)
        hits = self.searcher.search(
            request.agent_id, request.query, limit=request.top_k, domains=domains
        )
        if not should_answer(hits):
            hits = []
        return KnowledgeSearchResponse(
            agent_id=request.agent_id,
            effective_domains=domains,
            hits=[
                KnowledgeSearchHit(
                    entry_id=hit.entry_id,
                    knowledge_base_id=hit.knowledge_base_id,
                    domain=hit.domain,
                    title=hit.title,
                    content=hit.content,
                    score=hit.score,
                    source_type=hit.source_type,
                    source_ref=hit.source_ref,
                    matched_terms=hit.matched_terms,
                )
                for hit in hits
            ],
        )
