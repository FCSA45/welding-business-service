from typing import Literal

from pydantic import BaseModel, Field, field_validator


KnowledgeDomain = Literal["shared", "performance", "workshop", "inventory"]


class KnowledgeSearchRequest(BaseModel):
    agent_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,79}$")
    query: str = Field(min_length=1, max_length=12000)
    domains: list[KnowledgeDomain] | None = None
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator("domains")
    @classmethod
    def unique_domains(cls, domains: list[KnowledgeDomain] | None):
        if domains is None:
            return None
        return list(dict.fromkeys(domains))


class KnowledgeSearchHit(BaseModel):
    entry_id: int
    knowledge_base_id: int
    domain: KnowledgeDomain
    title: str
    content: str
    score: int
    source_type: str
    source_ref: str
    matched_terms: list[str]


class KnowledgeSearchResponse(BaseModel):
    agent_id: str
    effective_domains: list[KnowledgeDomain]
    hits: list[KnowledgeSearchHit]
