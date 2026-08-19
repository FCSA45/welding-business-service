import math
from dataclasses import dataclass
from threading import RLock

from app.knowledge.rag.embedding import TextEncoder
from app.knowledge.rag.splitter import OverlapTextSplitter


@dataclass(frozen=True)
class RagDocument:
    document_id: str
    title: str
    content: str
    department_code: str
    domain: str = "shared"
    source_ref: str = ""


@dataclass(frozen=True)
class RagHit:
    document_id: str
    chunk_index: int
    title: str
    content: str
    department_code: str
    domain: str
    source_ref: str
    score: float


@dataclass(frozen=True)
class _VectorChunk:
    document: RagDocument
    chunk_index: int
    content: str
    vector: tuple[float, ...]


class VectorKnowledgeIndex:
    """Thread-safe in-process demo index with authorization before scoring."""

    def __init__(self, encoder: TextEncoder, splitter: OverlapTextSplitter | None = None) -> None:
        self.encoder = encoder
        self.splitter = splitter or OverlapTextSplitter()
        self._chunks: tuple[_VectorChunk, ...] = ()
        self._lock = RLock()

    @property
    def chunk_count(self) -> int:
        with self._lock:
            return len(self._chunks)

    def rebuild(self, documents: list[RagDocument]) -> int:
        pending: list[tuple[RagDocument, int, str]] = []
        for document in documents:
            for index, content in enumerate(self.splitter.split(document.content)):
                pending.append((document, index, content))
        vectors = self.encoder.encode([f"{doc.title}\n{content}" for doc, _, content in pending]) if pending else []
        chunks = tuple(
            _VectorChunk(doc, index, content, tuple(float(value) for value in vector))
            for (doc, index, content), vector in zip(pending, vectors, strict=True)
        )
        with self._lock:
            self._chunks = chunks
        return len(chunks)

    def search(
        self, query: str, *, allowed_departments: frozenset[str], domains: set[str] | None = None,
        top_k: int = 5, minimum_score: float = 0.35,
    ) -> list[RagHit]:
        query_vector = self.encoder.encode([query])[0]
        with self._lock:
            snapshot = self._chunks
        scored: list[RagHit] = []
        for chunk in snapshot:
            department = chunk.document.department_code
            if department != "shared" and "*" not in allowed_departments and department not in allowed_departments:
                continue
            if domains and chunk.document.domain not in domains:
                continue
            score = self._cosine(query_vector, chunk.vector)
            if score < minimum_score:
                continue
            scored.append(RagHit(
                document_id=chunk.document.document_id, chunk_index=chunk.chunk_index,
                title=chunk.document.title, content=chunk.content,
                department_code=department, domain=chunk.document.domain,
                source_ref=chunk.document.source_ref, score=round(score, 4),
            ))
        scored.sort(key=lambda hit: (-hit.score, hit.document_id, hit.chunk_index))
        return scored[:top_k]

    @staticmethod
    def _cosine(left, right) -> float:
        if len(left) != len(right) or not left:
            return 0.0
        dot = sum(a * b for a, b in zip(left, right))
        norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
        return dot / norm if norm else 0.0
