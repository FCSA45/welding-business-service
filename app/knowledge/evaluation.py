from dataclasses import dataclass
from statistics import mean
from math import log2
from typing import Protocol

from app.knowledge.guardrails import should_answer


@dataclass(frozen=True)
class RetrievalCase:
    case_id: str
    query: str
    expected_source_refs: frozenset[str]
    allowed_domains: frozenset[str]
    expect_answer: bool = True


@dataclass(frozen=True)
class RetrievalCaseResult:
    case_id: str
    retrieved_source_refs: tuple[str, ...]
    first_relevant_rank: int | None
    leaked_domains: tuple[str, ...]
    precision_at_k: float
    ndcg_at_k: float
    answer_expected: bool
    answer_returned: bool


@dataclass(frozen=True)
class RetrievalEvaluation:
    case_count: int
    recall_at_k: float
    mean_reciprocal_rank: float
    domain_leak_count: int
    precision_at_k: float
    ndcg_at_k: float
    refusal_accuracy: float
    p95_latency_ms: float
    cases: tuple[RetrievalCaseResult, ...]


class RetrievalSearcher(Protocol):
    def search(self, agent_id: str, query: str, limit: int, domains: list[str]): ...


class RetrievalHarness:
    """Deterministic retrieval quality gate reusable across search backends."""

    def __init__(self, searcher: RetrievalSearcher, *, agent_id: str, top_k: int = 3) -> None:
        self.searcher = searcher
        self.agent_id = agent_id
        self.top_k = top_k

    def evaluate(self, cases: list[RetrievalCase]) -> RetrievalEvaluation:
        results = []
        reciprocal_ranks = []
        recalled = 0
        leak_count = 0
        precisions = []
        ndcgs = []
        refusal_checks = []
        latencies = []
        answerable_count = 0
        for case in cases:
            if hasattr(self.searcher, "search_with_trace"):
                hits, trace = self.searcher.search_with_trace(
                    self.agent_id, case.query, limit=self.top_k,
                    domains=sorted(case.allowed_domains),
                )
                latencies.append(trace.elapsed_ms)
            else:
                from time import perf_counter
                started = perf_counter()
                hits = self.searcher.search(
                    self.agent_id, case.query, limit=self.top_k,
                    domains=sorted(case.allowed_domains),
                )
                latencies.append((perf_counter() - started) * 1000)
            refs = tuple(hit.source_ref for hit in hits)
            rank = next(
                (index for index, ref in enumerate(refs, start=1) if ref in case.expected_source_refs),
                None,
            )
            leaked = tuple(
                sorted({hit.domain for hit in hits if hit.domain not in case.allowed_domains})
            )
            if case.expect_answer:
                answerable_count += 1
                recalled += int(rank is not None)
                reciprocal_ranks.append(0 if rank is None else 1 / rank)
            leak_count += len(leaked)
            relevant_count = sum(ref in case.expected_source_refs for ref in refs)
            precision = relevant_count / self.top_k
            dcg = sum(
                (1 / log2(index + 1)) if ref in case.expected_source_refs else 0
                for index, ref in enumerate(refs, start=1)
            )
            ideal_relevant = min(len(case.expected_source_refs), self.top_k)
            ideal_dcg = sum(1 / log2(index + 1) for index in range(1, ideal_relevant + 1))
            ndcg = 0 if ideal_dcg == 0 else dcg / ideal_dcg
            answer_returned = should_answer(hits)
            if not case.expect_answer:
                refusal_checks.append(not answer_returned)
            if case.expect_answer:
                precisions.append(precision)
                ndcgs.append(ndcg)
            results.append(RetrievalCaseResult(
                case.case_id, refs, rank, leaked, precision, ndcg,
                case.expect_answer, answer_returned,
            ))
        count = len(cases)
        return RetrievalEvaluation(
            case_count=count,
            recall_at_k=0 if answerable_count == 0 else recalled / answerable_count,
            mean_reciprocal_rank=0 if not reciprocal_ranks else mean(reciprocal_ranks),
            domain_leak_count=leak_count,
            precision_at_k=0 if not precisions else mean(precisions),
            ndcg_at_k=0 if not ndcgs else mean(ndcgs),
            refusal_accuracy=1.0 if not refusal_checks else mean(refusal_checks),
            p95_latency_ms=self._percentile(latencies, 0.95),
            cases=tuple(results),
        )

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float:
        if not values:
            return 0
        ordered = sorted(values)
        index = min(len(ordered) - 1, max(0, int(len(ordered) * percentile + 0.999) - 1))
        return ordered[index]

    @staticmethod
    def assert_quality(
        evaluation: RetrievalEvaluation,
        *,
        min_recall_at_k: float,
        min_mrr: float,
        min_ndcg: float = 0.8,
        min_refusal_accuracy: float = 1.0,
        max_p95_latency_ms: float = 100,
    ) -> None:
        assert evaluation.recall_at_k >= min_recall_at_k, evaluation
        assert evaluation.mean_reciprocal_rank >= min_mrr, evaluation
        assert evaluation.ndcg_at_k >= min_ndcg, evaluation
        assert evaluation.refusal_accuracy >= min_refusal_accuracy, evaluation
        assert evaluation.p95_latency_ms <= max_p95_latency_ms, evaluation
        assert evaluation.domain_leak_count == 0, evaluation
