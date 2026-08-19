"""Small, replaceable RAG core used by the knowledge-base demo."""

from app.knowledge.rag.index import RagDocument, RagHit, VectorKnowledgeIndex
from app.knowledge.rag.splitter import OverlapTextSplitter

__all__ = ["OverlapTextSplitter", "RagDocument", "RagHit", "VectorKnowledgeIndex"]
