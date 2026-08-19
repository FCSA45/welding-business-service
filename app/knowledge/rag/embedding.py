from collections.abc import Iterable
from threading import Lock
from typing import Protocol


class TextEncoder(Protocol):
    def encode(self, texts: list[str]) -> list[list[float]]: ...


class FastEmbedEncoder:
    """Lazy CPU encoder; the 90 MB Chinese model is downloaded only on first use."""

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5", cache_dir: str | None = None) -> None:
        self.model_name = model_name
        self.cache_dir = cache_dir
        self._model = None
        self._lock = Lock()

    def encode(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        vectors: Iterable = model.embed(texts, batch_size=16)
        return [vector.tolist() for vector in vectors]

    def _get_model(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is None:
                try:
                    from fastembed import TextEmbedding
                except ImportError as exc:
                    raise RuntimeError("RAG demo requires the optional fastembed dependency") from exc
                self._model = TextEmbedding(model_name=self.model_name, cache_dir=self.cache_dir)
        return self._model
