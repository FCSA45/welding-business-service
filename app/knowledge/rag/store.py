import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import KnowledgeBaseRow, KnowledgeChunkRow, KnowledgeDocumentRow
from app.knowledge.rag.embedding import TextEncoder
from app.knowledge.rag.parsers import DocumentParser
from app.knowledge.rag.splitter import OverlapTextSplitter


@dataclass(frozen=True)
class IngestResult:
    document_id: int
    content_hash: str
    chunk_count: int
    duplicate: bool


@dataclass(frozen=True)
class StoredRagHit:
    document_id: int
    chunk_id: int
    title: str
    content: str
    department_code: str
    domain: str
    source_ref: str
    score: float
    metadata: dict


class PersistentRagStore:
    """Database-backed ingestion and retrieval with scope filters applied in SQL."""

    def __init__(self, session: Session, encoder: TextEncoder, *, splitter=None, parser=None) -> None:
        self.session = session
        self.encoder = encoder
        self.splitter = splitter or OverlapTextSplitter()
        self.parser = parser or DocumentParser()

    def ingest_file(
        self, path: str | Path, *, knowledge_base_id: int, department_code: str,
        source_ref: str = "", metadata: dict | None = None,
    ) -> IngestResult:
        parsed = self.parser.parse(path)
        return self.ingest_text(
            title=parsed.title, content=parsed.content, source_type=parsed.source_type,
            knowledge_base_id=knowledge_base_id, department_code=department_code,
            source_ref=source_ref or str(path), metadata={**parsed.metadata, **(metadata or {})},
        )

    def ingest_text(
        self, *, title: str, content: str, source_type: str, knowledge_base_id: int,
        department_code: str, source_ref: str = "", metadata: dict | None = None,
    ) -> IngestResult:
        normalized = "\n".join(line.strip() for line in content.splitlines() if line.strip())
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        duplicate = self.session.scalar(select(KnowledgeDocumentRow).where(
            KnowledgeDocumentRow.knowledge_base_id == knowledge_base_id,
            KnowledgeDocumentRow.department_code == department_code,
            KnowledgeDocumentRow.content_hash == digest,
        ))
        if duplicate is not None:
            count = len(self.session.scalars(select(KnowledgeChunkRow).where(KnowledgeChunkRow.document_id == duplicate.id)).all())
            return IngestResult(duplicate.id, digest, count, True)

        chunks = self.splitter.split(normalized)
        vectors = self.encoder.encode([f"{title}\n{chunk}" for chunk in chunks])
        document = KnowledgeDocumentRow(
            knowledge_base_id=knowledge_base_id, title=title,
            department_code=department_code, source_type=source_type,
            source_ref=source_ref, content_hash=digest, metadata_json=metadata or {}, enabled=True,
        )
        self.session.add(document)
        self.session.flush()
        self.session.add_all([
            KnowledgeChunkRow(
                document_id=document.id, chunk_index=index, content=chunk,
                token_estimate=max(1, len(chunk) // 2), embedding_json=vector,
                metadata_json={"title": title, "department_code": department_code, **(metadata or {})},
            )
            for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
        ])
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing = self.session.scalar(select(KnowledgeDocumentRow).where(
                KnowledgeDocumentRow.knowledge_base_id == knowledge_base_id,
                KnowledgeDocumentRow.department_code == department_code,
                KnowledgeDocumentRow.content_hash == digest,
            ))
            if existing is None:
                raise
            count = len(self.session.scalars(select(KnowledgeChunkRow).where(KnowledgeChunkRow.document_id == existing.id)).all())
            return IngestResult(existing.id, digest, count, True)
        return IngestResult(document.id, digest, len(chunks), False)

    def search(
        self, query: str, *, agent_id: str, allowed_departments: frozenset[str],
        domains: list[str], top_k: int = 5, minimum_score: float = 0.35,
        candidate_limit: int = 1000,
    ) -> list[StoredRagHit]:
        department_filter = KnowledgeDocumentRow.department_code == "shared"
        if "*" in allowed_departments:
            department_filter = KnowledgeDocumentRow.department_code.is_not(None)
        elif allowed_departments:
            department_filter = or_(department_filter, KnowledgeDocumentRow.department_code.in_(allowed_departments))
        statement = (
            select(KnowledgeChunkRow, KnowledgeDocumentRow, KnowledgeBaseRow)
            .join(KnowledgeDocumentRow, KnowledgeDocumentRow.id == KnowledgeChunkRow.document_id)
            .join(KnowledgeBaseRow, KnowledgeBaseRow.id == KnowledgeDocumentRow.knowledge_base_id)
            .where(
                KnowledgeDocumentRow.enabled.is_(True), KnowledgeBaseRow.enabled.is_(True),
                or_(KnowledgeBaseRow.agent_id == agent_id, KnowledgeBaseRow.agent_id.is_(None)),
                KnowledgeBaseRow.domain.in_(domains), department_filter,
            )
            .limit(candidate_limit)
        )
        query_vector = self.encoder.encode([query])[0]
        hits: list[StoredRagHit] = []
        for chunk, document, knowledge_base in self.session.execute(statement):
            score = self._cosine(query_vector, chunk.embedding_json)
            if score >= minimum_score:
                hits.append(StoredRagHit(
                    document.id, chunk.id, document.title, chunk.content,
                    document.department_code, knowledge_base.domain, document.source_ref,
                    round(score, 4), {**document.metadata_json, **chunk.metadata_json},
                ))
        hits.sort(key=lambda hit: (-hit.score, hit.chunk_id))
        return hits[:top_k]

    @staticmethod
    def _cosine(left, right) -> float:
        if not left or len(left) != len(right):
            return 0.0
        dot = sum(float(a) * float(b) for a, b in zip(left, right))
        norm = math.sqrt(sum(float(a) ** 2 for a in left)) * math.sqrt(sum(float(b) ** 2 for b in right))
        return dot / norm if norm else 0.0
