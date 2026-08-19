from fastapi import APIRouter, Depends

from app.api.dependencies import get_knowledge_service, verify_business_api_key
from app.knowledge.contracts import KnowledgeSearchRequest, KnowledgeSearchResponse
from app.knowledge.service import KnowledgeService


router = APIRouter(
    prefix="/knowledge",
    tags=["knowledge"],
    dependencies=[Depends(verify_business_api_key)],
)


@router.post("/search", response_model=KnowledgeSearchResponse)
def search_knowledge(
    request: KnowledgeSearchRequest,
    service: KnowledgeService = Depends(get_knowledge_service),
) -> KnowledgeSearchResponse:
    return service.search(request)
