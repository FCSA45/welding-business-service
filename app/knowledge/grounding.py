import re


def source_refs(hits) -> list[str]:
    """Return stable, de-duplicated evidence identifiers for this retrieval only."""
    return list(dict.fromkeys(hit.source_ref for hit in hits if hit.source_ref))


def append_verified_sources(answer: str, hits) -> str:
    """Attach server-controlled citations so the model cannot invent evidence links."""
    refs = source_refs(hits)
    cleaned = answer.strip()
    if not refs:
        return cleaned
    citation = "、".join(f"[{ref}]" for ref in refs)
    return f"{cleaned}\n\n参考来源：{citation}"


def cited_refs(answer: str) -> set[str]:
    return set(re.findall(r"\[([^\[\]\r\n]{1,500})\]", answer))


def citations_are_grounded(answer: str, hits) -> bool:
    """Reject citations not present in the current authorized retrieval."""
    return cited_refs(answer).issubset(set(source_refs(hits)))
