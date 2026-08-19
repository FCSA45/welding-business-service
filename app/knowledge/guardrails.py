import re
from dataclasses import dataclass


@dataclass(frozen=True)
class QuerySafetyDecision:
    allowed: bool
    reason: str


_INJECTION_PATTERNS = (
    r"忽略.{0,12}(规则|指令|权限|系统提示)",
    r"绕过.{0,12}(权限|鉴权|知识域|限制)",
    r"(输出|泄露|显示).{0,12}(密钥|密码|token|system prompt|系统提示词)",
    r"ignore.{0,20}(previous|system|instruction|policy)",
    r"reveal.{0,20}(secret|token|password|system prompt)",
)


def inspect_query(query: str) -> QuerySafetyDecision:
    normalized = re.sub(r"\s+", " ", query).strip().lower()
    for pattern in _INJECTION_PATTERNS:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            return QuerySafetyDecision(False, "prompt_injection_or_secret_exfiltration")
    return QuerySafetyDecision(True, "allowed")


def should_answer(hits, *, min_score: int = 18, min_matched_terms: int = 1) -> bool:
    if not hits:
        return False
    top = hits[0]
    strong_reasons = {"title_phrase", "content_phrase", "metadata_phrase", "tag", "original_term", "semantic_vector"}
    match_reasons = getattr(top, "match_reasons", None)
    has_direct_evidence = (
        True if match_reasons is None else bool(strong_reasons.intersection(match_reasons))
    )
    return (
        top.score >= min_score
        and len(top.matched_terms) >= min_matched_terms
        and has_direct_evidence
    )
