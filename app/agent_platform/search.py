import math
import re
import unicodedata
from time import perf_counter
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from app.agent_platform.repository import KnowledgeRepository


@dataclass(frozen=True)
class QueryPlan:
    original_query: str
    intent: str
    rewritten_queries: list[str]
    terms: set[str]
    filters: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgeHit:
    entry_id: int
    knowledge_base_id: int
    knowledge_base_name: str
    domain: str
    title: str
    content: str
    score: int
    intent: str
    tags: list[str]
    metadata: dict[str, Any]
    matched_terms: list[str]
    match_reasons: list[str]
    source_type: str
    source_ref: str


@dataclass(frozen=True)
class RetrievalTrace:
    original_query: str
    intent: str
    rewritten_queries: tuple[str, ...]
    effective_domains: tuple[str, ...]
    candidate_count: int
    returned_count: int
    elapsed_ms: float
    results: tuple[dict[str, Any], ...]


_INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "report_generation": (
        "日报",
        "周报",
        "月报",
        "报表",
        "总结",
        "汇总",
        "绩效",
        "业绩",
        "report",
        "summary",
    ),
    "rule_lookup": (
        "规则",
        "标准",
        "口径",
        "怎么判断",
        "如何判断",
        "审核",
        "规范",
        "policy",
        "rule",
    ),
    "data_status": (
        "数据",
        "字段",
        "缺少",
        "没有数据",
        "同步",
        "来源",
        "接口",
        "字段",
        "schema",
        "source",
    ),
    "troubleshooting": (
        "失败",
        "报错",
        "异常",
        "为什么",
        "无法",
        "问题",
        "原因",
        "error",
        "failed",
    ),
    "action_request": (
        "生成",
        "创建",
        "发送",
        "推送",
        "执行",
        "帮我",
        "请",
        "run",
        "create",
    ),
}

_INTENT_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "report_generation": ("日报 周报 月报 报表 汇总 绩效 运营 完成量",),
    "rule_lookup": ("规则 标准 口径 判断条件 审核规范",),
    "data_status": ("数据源 字段 同步 表结构 缺失 配置",),
    "troubleshooting": ("异常 错误 失败 原因 修复 排查",),
    "action_request": ("操作 执行 生成 输出 推送",),
    "general_question": ("说明 文档 知识 常见问题",),
}

_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "what",
    "how",
    "why",
    "请问",
    "一下",
    "这个",
    "那个",
    "可以",
    "帮我",
    "请",
}

_QUERY_SYNONYMS: dict[str, tuple[str, ...]] = {
    "快到期": ("临期", "交期", "计划完成时间"),
    "快过期": ("临期", "交期", "计划完成时间"),
    "来不及交货": ("延期", "交期风险", "逾期"),
    "来不及交": ("延期", "进度落后", "交期风险"),
    "不能按时完成": ("延期", "进度落后", "交期风险"),
    "机器报警": ("设备异常", "设备报警", "故障"),
    "机器坏了": ("设备异常", "设备故障", "停机"),
    "没报工": ("未报工", "进度停滞", "长时间无进度"),
    "没有报工": ("未报工", "进度停滞", "长时间无进度"),
    "做得慢": ("进度落后", "完成率偏低", "延期风险"),
}


def normalize_dialogue_query(value: str) -> str:
    """Normalize common chat noise without changing business meaning."""
    normalized = unicodedata.normalize("NFKC", value).lower().strip()
    normalized = re.sub(r"([!?！？。，,.])\1+", r"\1", normalized)
    normalized = re.sub(r"([\u4e00-\u9fff])\1{2,}", r"\1\1", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", normalize_dialogue_query(value))


def tokenize(value: str) -> list[str]:
    lowered = value.lower()
    words = re.findall(r"[a-z0-9][a-z0-9_-]{1,}|[\u4e00-\u9fff]{2,}", lowered)
    tokens: list[str] = []
    for word in words:
        if word in _STOPWORDS:
            continue
        tokens.append(word)
        if re.fullmatch(r"[\u4e00-\u9fff]{3,}", word):
            tokens.extend(word[index : index + 2] for index in range(len(word) - 1))
    compact = normalize_text(value)
    if 2 <= len(compact) <= 30:
        tokens.append(compact)
    return [token for token in tokens if token and token not in _STOPWORDS]


def _char_ngrams(value: str, size: int = 3) -> Counter[str]:
    compact = normalize_text(value)
    if not compact:
        return Counter()
    if len(compact) <= size:
        return Counter({compact: 1})
    return Counter(compact[index : index + size] for index in range(len(compact) - size + 1))


def _dialogue_ngrams(value: str) -> Counter[str]:
    """Blend bigrams and trigrams so one typo does not destroy semantic overlap."""
    grams = _char_ngrams(value, 2)
    grams.update({term: count * 2 for term, count in _char_ngrams(value, 3).items()})
    return grams


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(count * right.get(term, 0) for term, count in left.items())
    left_norm = math.sqrt(sum(count * count for count in left.values()))
    right_norm = math.sqrt(sum(count * count for count in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _split_tags(value: str | None) -> list[str]:
    if not value:
        return []
    return [
        item.strip().lower()
        for item in re.split(r"[,，;；\s]+", value)
        if item.strip()
    ]


def _metadata_from_entry(entry) -> dict[str, Any]:
    metadata = getattr(entry, "metadata_json", None)
    return metadata if isinstance(metadata, dict) else {}


def _entry_tags(entry, metadata: dict[str, Any]) -> list[str]:
    tags = set(_split_tags(getattr(entry, "tags", "")))
    for key in ("tags", "keywords", "intent", "agent", "business_object", "period", "source"):
        value = metadata.get(key)
        if isinstance(value, str):
            tags.update(_split_tags(value))
        elif isinstance(value, list):
            tags.update(str(item).strip().lower() for item in value if str(item).strip())
    for hashtag in re.findall(r"#([A-Za-z0-9_\-\u4e00-\u9fff]{2,})", f"{entry.title}\n{entry.content}"):
        tags.add(hashtag.lower())
    return sorted(tags)


def infer_intent(query: str) -> str:
    normalized = normalize_text(query)
    best_intent = "general_question"
    best_score = 0
    for intent, keywords in _INTENT_KEYWORDS.items():
        score = sum(1 for keyword in keywords if normalize_text(keyword) in normalized)
        if score > best_score:
            best_intent = intent
            best_score = score
    return best_intent


def build_query_plan(query: str) -> QueryPlan:
    cleaned_query = normalize_dialogue_query(query)
    intent = infer_intent(cleaned_query)
    rewrites = [cleaned_query]
    compact = re.sub(r"^(请问|请|帮我|麻烦|能不能|可以|我想问下|想问一下)", "", cleaned_query)
    compact = re.sub(r"(一下|吗|呢|吧)[？?]?$", "", compact).strip()
    if compact and compact not in rewrites:
        rewrites.append(compact)
    normalized_query = normalize_text(cleaned_query)
    for phrase, synonyms in _QUERY_SYNONYMS.items():
        if normalize_text(phrase) in normalized_query:
            rewrites.extend(item for item in synonyms if item not in rewrites)
    rewrites.extend(item for item in _INTENT_EXPANSIONS.get(intent, ()) if item not in rewrites)
    terms = set()
    for rewrite in rewrites:
        terms.update(tokenize(rewrite))
    return QueryPlan(
        original_query=cleaned_query,
        intent=intent,
        rewritten_queries=rewrites,
        terms=terms,
    )


class KnowledgeSearchService:
    def __init__(self, repository: KnowledgeRepository, query_enhancer=None) -> None:
        self.repository = repository
        self.query_enhancer = query_enhancer

    def search(
        self,
        agent_id: str,
        query: str,
        limit: int = 5,
        domains: list[str] | None = None,
    ) -> list[KnowledgeHit]:
        hits, _ = self.search_with_trace(agent_id, query, limit=limit, domains=domains)
        return hits

    def search_with_trace(
        self,
        agent_id: str,
        query: str,
        limit: int = 5,
        domains: list[str] | None = None,
    ) -> tuple[list[KnowledgeHit], RetrievalTrace]:
        started = perf_counter()
        plan = build_query_plan(query)
        if self.query_enhancer is not None:
            plan = self.query_enhancer.enhance(query, plan)
        candidates = self.repository.list_search_candidates(agent_id, domains=domains)
        if not candidates:
            return [], RetrievalTrace(
                original_query=query, intent=plan.intent,
                rewritten_queries=tuple(plan.rewritten_queries),
                effective_domains=tuple(domains or ()), candidate_count=0,
                returned_count=0, elapsed_ms=round((perf_counter() - started) * 1000, 3),
                results=(),
            )

        document_tokens: list[set[str]] = []
        documents: list[tuple[Any, Any, str, dict[str, Any], list[str]]] = []
        for entry, knowledge_base in candidates:
            metadata = _metadata_from_entry(entry)
            tags = _entry_tags(entry, metadata)
            searchable = self._searchable_text(entry, knowledge_base, metadata, tags)
            documents.append((entry, knowledge_base, searchable, metadata, tags))
            document_tokens.append(set(tokenize(searchable)))

        idf = self._inverse_document_frequency(document_tokens)
        query_vector = _dialogue_ngrams(" ".join(plan.rewritten_queries))
        scored: list[KnowledgeHit] = []
        for entry, knowledge_base, searchable, metadata, tags in documents:
            score, matched_terms, reasons = self._score_document(
                plan=plan,
                entry=entry,
                searchable=searchable,
                tags=tags,
                metadata=metadata,
                idf=idf,
                query_vector=query_vector,
            )
            if score <= 0:
                continue
            scored.append(
                KnowledgeHit(
                    entry_id=entry.id,
                    knowledge_base_id=knowledge_base.id,
                    knowledge_base_name=knowledge_base.name,
                    domain=knowledge_base.domain,
                    title=entry.title,
                    content=entry.content,
                    score=round(score),
                    intent=plan.intent,
                    tags=tags,
                    metadata=metadata,
                    matched_terms=matched_terms[:12],
                    match_reasons=reasons,
                    source_type=entry.source_type,
                    source_ref=entry.source_ref,
                )
            )

        scored.sort(key=lambda item: (-item.score, item.entry_id))
        hits = scored[:limit]
        trace = RetrievalTrace(
            original_query=query,
            intent=plan.intent,
            rewritten_queries=tuple(plan.rewritten_queries),
            effective_domains=tuple(domains or ()),
            candidate_count=len(candidates),
            returned_count=len(hits),
            elapsed_ms=round((perf_counter() - started) * 1000, 3),
            results=tuple(
                {
                    "source_ref": hit.source_ref,
                    "domain": hit.domain,
                    "score": hit.score,
                    "matched_terms": hit.matched_terms,
                    "match_reasons": hit.match_reasons,
                }
                for hit in hits
            ),
        )
        return hits, trace

    @staticmethod
    def _searchable_text(entry, knowledge_base, metadata: dict[str, Any], tags: list[str]) -> str:
        metadata_text = " ".join(
            str(value)
            for value in metadata.values()
            if isinstance(value, (str, int, float, bool))
        )
        return "\n".join(
            [
                knowledge_base.name,
                knowledge_base.description,
                entry.title,
                entry.content,
                entry.source_type,
                entry.source_ref,
                " ".join(tags),
                metadata_text,
            ]
        )

    @staticmethod
    def _inverse_document_frequency(documents: list[set[str]]) -> dict[str, float]:
        total = max(len(documents), 1)
        frequencies: Counter[str] = Counter()
        for terms in documents:
            frequencies.update(terms)
        return {
            term: math.log((total + 1) / (count + 0.5)) + 1
            for term, count in frequencies.items()
        }

    @staticmethod
    def _score_document(
        *,
        plan: QueryPlan,
        entry,
        searchable: str,
        tags: list[str],
        metadata: dict[str, Any],
        idf: dict[str, float],
        query_vector: Counter[str],
    ) -> tuple[float, list[str], list[str]]:
        normalized_searchable = normalize_text(searchable)
        title = normalize_text(entry.title)
        content = normalize_text(entry.content)
        token_counts = Counter(tokenize(searchable))
        original_terms = set(tokenize(plan.original_query))

        exact_score = 0.0
        reasons: list[str] = []
        for rewrite in plan.rewritten_queries:
            normalized_rewrite = normalize_text(rewrite)
            if len(normalized_rewrite) < 2:
                continue
            if normalized_rewrite in title:
                exact_score += 70
                reasons.append("title_phrase")
            elif normalized_rewrite in content:
                exact_score += 45
                reasons.append("content_phrase")
            elif normalized_rewrite in normalized_searchable:
                exact_score += 25
                reasons.append("metadata_phrase")

        lexical_score = 0.0
        matched_terms: list[str] = []
        for term in plan.terms:
            term_count = token_counts.get(term, 0)
            if term_count <= 0 and term not in normalized_searchable:
                continue
            matched_terms.append(term)
            lexical_score += (1 + math.log(max(term_count, 1))) * idf.get(term, 1.0) * 8
            if term in original_terms:
                reasons.append("original_term")

        tag_score = 0.0
        tag_set = set(tags)
        metadata_intent = str(metadata.get("intent") or "").lower()
        if plan.intent in tag_set or plan.intent == metadata_intent:
            tag_score += 30
            reasons.append("intent_tag")
        for term in plan.terms:
            if term in tag_set:
                tag_score += 14
                reasons.append("tag")

        semantic_score = _cosine(query_vector, _dialogue_ngrams(searchable)) * 60
        if semantic_score >= 12:
            reasons.append("semantic_overlap")

        score = exact_score + lexical_score + tag_score + semantic_score
        unique_reasons = list(dict.fromkeys(reasons))
        return score, sorted(set(matched_terms)), unique_reasons
