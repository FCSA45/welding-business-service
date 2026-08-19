from functools import lru_cache

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.dependencies import verify_admin_api_key, verify_business_api_key
from app.config import Settings, get_settings
from app.knowledge.policy import resolve_allowed_domains
from app.knowledge.rag.embedding import FastEmbedEncoder
from app.knowledge.rag.index import RagDocument, VectorKnowledgeIndex
from app.knowledge.rag.splitter import OverlapTextSplitter
from app.workshop.access import resolve_department_scope


router = APIRouter(prefix="/knowledge/rag-demo", tags=["knowledge-rag-demo"])


class DemoDocument(BaseModel):
    document_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=200_000)
    department_code: str = Field(min_length=1, max_length=100)
    domain: str = Field(default="shared", pattern="^(shared|workshop|performance|inventory)$")
    source_ref: str = Field(default="", max_length=500)


class RebuildRequest(BaseModel):
    documents: list[DemoDocument] = Field(max_length=500)


class SearchRequest(BaseModel):
    agent_id: str = Field(default="workshop-agent", pattern=r"^[a-z0-9][a-z0-9-]{1,79}$")
    requester_id: str = Field(min_length=1, max_length=200)
    chat_id: str = Field(default="", max_length=200)
    query: str = Field(min_length=1, max_length=4000)
    domains: list[str] | None = None
    top_k: int = Field(default=5, ge=1, le=20)


@lru_cache
def _index() -> VectorKnowledgeIndex:
    settings = get_settings()
    return VectorKnowledgeIndex(
        FastEmbedEncoder(settings.rag_embedding_model, settings.rag_model_cache_dir or None),
        OverlapTextSplitter(settings.rag_chunk_size, settings.rag_chunk_overlap),
    )


@router.post("/rebuild", dependencies=[Depends(verify_admin_api_key)])
def rebuild(request: RebuildRequest) -> dict:
    count = _index().rebuild([RagDocument(**document.model_dump()) for document in request.documents])
    return {"document_count": len(request.documents), "chunk_count": count}


@router.post("/search", dependencies=[Depends(verify_business_api_key)])
def search(request: SearchRequest, settings: Settings = Depends(get_settings)) -> dict:
    scope = resolve_department_scope(settings, request.requester_id, chat_id=request.chat_id)
    domains = set(resolve_allowed_domains(request.agent_id, request.domains))
    hits = _index().search(
        request.query, allowed_departments=scope.allowed_departments,
        domains=domains, top_k=request.top_k, minimum_score=settings.rag_minimum_score,
    )
    return {"query": request.query, "hits": [hit.__dict__ for hit in hits]}
