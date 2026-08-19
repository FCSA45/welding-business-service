"""Rule-first intent and entity parser for business routing.

The parser deliberately keeps extraction deterministic and structured.  A model
fallback can be added above this layer later, but it should receive this parsed
contract and never replace the hard rules for dates, departments, or periods.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from app.business_routing.intents import BusinessIntent
from app.business_routing.models import BusinessRequest
from app.business_routing.rewriter import QueryRewriter


@dataclass(frozen=True)
class PeriodRule:
    keywords: tuple[str, ...]
    period: str
    anchor_days_ago: int


@dataclass(frozen=True)
class ParsedDate:
    value: str = ""
    source: str = ""


class BusinessIntentParser:
    """Extract entities first, then classify using the extracted rule signals."""

    _department = re.compile(r"(?P<department>[\u4e00-\u9fffA-Za-z0-9_-]{1,20}部)")
    _explicit_date = re.compile(
        r"(?P<year>\d{4})\s*(?:年|[./-])\s*"
        r"(?P<month>\d{1,2})\s*(?:月|[./-])\s*"
        r"(?P<day>\d{1,2})\s*(?:日|号)?"
    )
    _compact_date = re.compile(
        r"(?<!\d)(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})(?!\d)"
    )
    _month_day = re.compile(
        r"(?<!\d)(?P<month>\d{1,2})月(?P<day>\d{1,2})[日号]?"
    )

    _period_rules = (
        PeriodRule(("三日前", "三天前", "大前天"), "three_days_ago", 3),
        PeriodRule(("二日前", "两日前", "前两日", "前两天", "前天"), "day_before_yesterday", 2),
        PeriodRule(("昨日", "昨天"), "yesterday", 1),
    )
    _report_keywords = (
        "生产订单日报",
        "生产订单报表",
        "订单日报",
        "订单报表",
        "日报",
        "报表",
        "订单",
    )
    _work_report_keywords = ("报工",)
    _ignored_keyword_phrases = ("订单号", "订单编号", "订单名称")
    _department_prefixes = (
        "请帮我生成",
        "请帮我查看",
        "请给我",
        "帮我生成",
        "帮我查看",
        "生成",
        "查询",
        "查看",
        "今天",
        "昨日",
        "昨天",
        "前两日",
        "前两天",
        "前两天的",
        "前两日的",
        "大前天",
        "三日前的",
        "三天前的",
        "二日前的",
        "两日前的",
        "前天的",
    )

    def __init__(
        self,
        rewriter: QueryRewriter | None = None,
        *,
        today: date | None = None,
    ) -> None:
        self.rewriter = rewriter or QueryRewriter()
        self._today = today

    def parse(self, query: str) -> BusinessRequest:
        rewritten = self.rewriter.rewrite(query)
        parsed_date = self._parse_date(rewritten)
        department = self._extract_department(rewritten)
        period, anchor_days_ago = self._extract_period(rewritten)
        report_keywords = self._match_keywords(rewritten, self._report_keywords)
        work_report = bool(self._match_keywords(rewritten, self._work_report_keywords))
        report = bool(report_keywords)

        if work_report and report:
            effective_period = period or "yesterday"
            effective_anchor = anchor_days_ago if period else 1
            return self._request(
                query,
                rewritten,
                intent=BusinessIntent.WORKSHOP_DEPARTMENT_WORK_REPORT,
                department=department,
                period=effective_period,
                output_template="wecom_work_report",
                entities={
                    "department": department,
                    "period": effective_period,
                    "anchor_days_ago": str(effective_anchor),
                    "statistics_date": parsed_date.value,
                },
            )

        if report:
            # A department order-daily-report request without an explicit
            # date means yesterday. It must stay on the deterministic report
            # route and must not fall through to the general model path.
            effective_period = period or ("explicit_date" if parsed_date.value else "yesterday")
            return self._request(
                query,
                rewritten,
                intent=BusinessIntent.WORKSHOP_DEPARTMENT_DAILY_REPORT,
                department=department,
                period=effective_period,
                output_template="wecom_department_report",
                entities={
                    "department": department,
                    "period": effective_period,
                    "anchor_days_ago": str(anchor_days_ago if period else 1),
                    "statistics_date": parsed_date.value,
                },
            )

        return BusinessRequest(
            original_query=query,
            rewritten_query=rewritten,
            intent=BusinessIntent.GENERAL_CHAT,
            business_module="agent_platform",
            confidence=0.6,
        )

    @staticmethod
    def _request(
        original_query: str,
        rewritten_query: str,
        *,
        intent: str,
        department: str,
        period: str,
        output_template: str,
        entities: dict[str, str],
    ) -> BusinessRequest:
        return BusinessRequest(
            original_query=original_query,
            rewritten_query=rewritten_query,
            intent=intent,
            business_module="workshop",
            department=department,
            period=period,
            output_template=output_template,
            confidence=1.0,
            entities=entities,
        )

    def _extract_department(self, rewritten: str) -> str:
        value = rewritten
        changed = True
        while changed:
            changed = False
            for prefix in self._department_prefixes:
                if value.startswith(prefix):
                    value = value[len(prefix) :]
                    changed = True
                    break
        match = self._department.search(value)
        return match.group("department") if match else ""

    def _extract_period(self, rewritten: str) -> tuple[str, int]:
        matches: list[tuple[int, PeriodRule]] = []
        for rule in self._period_rules:
            for keyword in rule.keywords:
                position = rewritten.find(keyword)
                if position >= 0:
                    matches.append((position, rule))
        if not matches:
            return "", 0
        _, rule = min(matches, key=lambda item: (item[0], -len(item[1].keywords[0])))
        return rule.period, rule.anchor_days_ago

    @classmethod
    def _match_keywords(cls, rewritten: str, keywords: tuple[str, ...]) -> set[str]:
        """Match configured phrases with longest-match and suffix guards.

        This avoids treating ``订单`` as a hit inside ``订单号`` while still
        matching compound phrases such as ``订单日报``.
        """
        lexicon = sorted(
            set(keywords) | set(cls._ignored_keyword_phrases),
            key=len,
            reverse=True,
        )
        matched: set[str] = set()
        index = 0
        while index < len(rewritten):
            candidate = next(
                (term for term in lexicon if rewritten.startswith(term, index)),
                None,
            )
            if candidate is None:
                index += 1
                continue
            index += len(candidate)
            if candidate in cls._ignored_keyword_phrases:
                continue
            matched.add(candidate)
        return matched

    def _parse_date(self, rewritten: str) -> ParsedDate:
        match = self._explicit_date.search(rewritten) or self._compact_date.search(rewritten)
        if match:
            value = self._valid_date(
                int(match.group("year")),
                int(match.group("month")),
                int(match.group("day")),
            )
            return ParsedDate(value, "explicit") if value else ParsedDate()

        match = self._month_day.search(rewritten)
        if not match:
            return ParsedDate()
        month = int(match.group("month"))
        day = int(match.group("day"))
        today = self._today or date.today()
        for year in range(today.year, today.year - 8, -1):
            value = self._valid_date(year, month, day)
            if value and date.fromisoformat(value) <= today:
                return ParsedDate(value, "month_day")
        return ParsedDate()

    @staticmethod
    def _valid_date(year: int, month: int, day: int) -> str:
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return ""
