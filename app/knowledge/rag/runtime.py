from functools import lru_cache

from app.config import get_settings
from app.knowledge.rag.embedding import FastEmbedEncoder


@lru_cache
def get_rag_encoder() -> FastEmbedEncoder:
    settings = get_settings()
    return FastEmbedEncoder(settings.rag_embedding_model, settings.rag_model_cache_dir or None)
