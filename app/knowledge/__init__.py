"""Shared knowledge contracts and access control for all business agents."""

from app.knowledge.contracts import KnowledgeSearchRequest, KnowledgeSearchResponse
from app.knowledge.service import KnowledgeService

__all__ = ["KnowledgeSearchRequest", "KnowledgeSearchResponse", "KnowledgeService"]
