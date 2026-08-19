import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.api.dependencies import verify_admin_api_key, verify_business_api_key
from app.config import Settings, get_settings
from app.db.session import get_db_session
from app.errors import AppError
from app.knowledge.policy import resolve_allowed_domains
from app.knowledge.rag.parsers import DocumentParser
from app.knowledge.rag.runtime import get_rag_encoder
from app.knowledge.rag.splitter import OverlapTextSplitter
from app.knowledge.rag.store import PersistentRagStore
from app.workshop.access import resolve_department_scope


router = APIRouter(prefix="/knowledge/rag", tags=["knowledge-rag"])


def _store(session: Session, settings: Settings) -> PersistentRagStore:
    return PersistentRagStore(
        session, get_rag_encoder(),
        splitter=OverlapTextSplitter(settings.rag_chunk_size, settings.rag_chunk_overlap),
    )


@router.post("/documents", dependencies=[Depends(verify_admin_api_key)])
async def ingest_document(
    file: UploadFile = File(...), knowledge_base_id: int = Form(...),
    department_code: str = Form(...), source_ref: str = Form(""), metadata_json: str = Form("{}"),
    settings: Settings = Depends(get_settings), session: Session = Depends(get_db_session),
) -> dict:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in DocumentParser.supported_extensions:
        raise AppError("RAG_FILE_TYPE_UNSUPPORTED", f"不支持的文件格式：{suffix or '无扩展名'}", status_code=400)
    payload = await file.read(settings.rag_max_upload_bytes + 1)
    if len(payload) > settings.rag_max_upload_bytes:
        raise AppError("RAG_FILE_TOO_LARGE", "知识文档超过上传大小限制", status_code=413)
    try:
        metadata = json.loads(metadata_json)
        if not isinstance(metadata, dict):
            raise ValueError
    except (json.JSONDecodeError, ValueError) as exc:
        raise AppError("RAG_METADATA_INVALID", "metadata_json 必须是 JSON 对象", status_code=400) from exc
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
            temporary.write(payload)
            temporary_path = Path(temporary.name)
        result = _store(session, settings).ingest_file(
            temporary_path, knowledge_base_id=knowledge_base_id,
            department_code=department_code.strip(), source_ref=source_ref or (file.filename or ""),
            metadata={"original_file_name": file.filename or "", **metadata},
        )
        return result.__dict__
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


@router.post("/search", dependencies=[Depends(verify_business_api_key)])
def search_documents(
    query: str, requester_id: str, agent_id: str = "workshop-agent", chat_id: str = "",
    top_k: int = 5, settings: Settings = Depends(get_settings),
    session: Session = Depends(get_db_session),
) -> dict:
    scope = resolve_department_scope(settings, requester_id, chat_id=chat_id)
    domains = resolve_allowed_domains(agent_id, None)
    hits = _store(session, settings).search(
        query, agent_id=agent_id, allowed_departments=scope.allowed_departments,
        domains=domains, top_k=min(max(top_k, 1), 20), minimum_score=settings.rag_minimum_score,
    )
    return {"query": query, "hits": [hit.__dict__ for hit in hits]}
