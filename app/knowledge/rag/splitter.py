import re


class OverlapTextSplitter:
    """Paragraph-aware overlapping splitter inspired by Haystack's DocumentSplitter."""

    def __init__(self, chunk_size: int = 700, overlap: int = 100) -> None:
        if chunk_size < 100 or overlap < 0 or overlap >= chunk_size:
            raise ValueError("chunk_size must be >= 100 and 0 <= overlap < chunk_size")
        self.chunk_size = chunk_size
        self.overlap = overlap

    def split(self, text: str) -> list[str]:
        normalized = re.sub(r"\r\n?", "\n", text or "").strip()
        if not normalized:
            return []
        units = [item.strip() for item in re.split(r"(?<=[。！？!?；;])|\n+", normalized) if item.strip()]
        chunks: list[str] = []
        current = ""
        for unit in units:
            if unit.startswith("#") and current:
                chunks.append(current)
                current = unit + "\n"
                continue
            if len(unit) > self.chunk_size:
                if current:
                    chunks.append(current)
                    current = ""
                chunks.extend(self._split_long(unit))
                continue
            candidate = current + unit
            if current and len(candidate) > self.chunk_size:
                chunks.append(current)
                current = current[-self.overlap :] + unit if self.overlap else unit
            else:
                current = candidate + ("\n" if unit.startswith("#") else "")
        if current:
            chunks.append(current)
        return list(dict.fromkeys(chunk.strip() for chunk in chunks if chunk.strip()))

    def _split_long(self, text: str) -> list[str]:
        step = self.chunk_size - self.overlap
        return [text[start : start + self.chunk_size] for start in range(0, len(text), step)]
