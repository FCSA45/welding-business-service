"""Deterministic query normalization before intent classification."""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Match

from app.agent_platform.search import normalize_dialogue_query


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RewriteRule:
    """A configuration-only synonym rule."""

    name: str
    phrases: tuple[str, ...]
    replacement: str
    priority: int = 0


@dataclass(frozen=True)
class PrefixRule:
    """A configuration-only leading courtesy phrase rule."""

    name: str
    phrases: tuple[str, ...]
    priority: int = 0


class QueryRewriter:
    """Normalize equivalent user phrases without changing business meaning."""

    MAX_QUERY_LENGTH = 4096
    _LEADING_NOISE = " \t\r\n,，。.!！？；;：:、"
    _COURTESY_SUFFIXES = ("谢谢你", "谢谢", "辛苦了", "感谢")
    _WORD_CHAR_CLASS = r"A-Za-z0-9_"

    PREFIX_RULES = (
        PrefixRule(
            "polite_request",
            ("请帮我看看", "请帮我查看", "请帮我生成", "请帮我", "麻烦", "能不能", "可以", "帮我", "给我", "我要", "我想看", "看看", "请"),
            priority=100,
        ),
    )
    REWRITE_RULES = (
        RewriteRule("day_before_yesterday", ("前天",), "二日前", priority=30),
        RewriteRule("three_days_ago", ("大前天",), "三日前", priority=40),
        RewriteRule("yesterday", ("昨儿", "昨天"), "昨日", priority=20),
        RewriteRule("previous_two_days", ("过去两天", "最近两天"), "前两日", priority=20),
        RewriteRule(
            "order_daily_report",
            ("生产订单报表", "生产订单日报", "订单报表", "订单日表"),
            "订单日报",
            priority=50,
        ),
        RewriteRule("department_alias", ("车间部门",), "部门", priority=10),
    )

    def __init__(self) -> None:
        self._prefix_pattern, self._prefix_lookup = self._compile_prefix_rules(self.PREFIX_RULES)
        self._synonym_pattern, self._synonym_lookup = self._compile_rewrite_rules(
            self.REWRITE_RULES
        )

    def rewrite(self, query: str | None) -> str:
        """Return a bounded, normalized query; empty input is a valid result."""
        if not isinstance(query, str):
            logger.warning("Business query rewrite skipped invalid input type=%s", type(query).__name__)
            return ""

        original_length = len(query)
        if original_length > self.MAX_QUERY_LENGTH:
            logger.warning(
                "Business query truncated original_length=%s max_length=%s",
                original_length,
                self.MAX_QUERY_LENGTH,
            )
            query = query[: self.MAX_QUERY_LENGTH]

        value = normalize_dialogue_query(query)
        value = self._strip_boundary_noise(value)
        value, prefix_names = self._remove_polite_prefix(value)
        value = self._strip_boundary_noise(value)
        value, synonym_names = self._rewrite_synonyms(value)
        value = self._strip_boundary_noise(value)
        value = self._remove_courtesy_suffix(value)
        value = "".join(value.split())
        value = self._strip_boundary_noise(value)

        logger.info(
            "Business query rewritten rewritten=%r rules=%s",
            value,
            tuple(prefix_names + synonym_names),
        )
        return value

    @classmethod
    def _compile_prefix_rules(
        cls, rules: tuple[PrefixRule, ...]
    ) -> tuple[re.Pattern[str], dict[str, PrefixRule]]:
        ordered = cls._ordered_phrases(rules)
        alternatives = "|".join(re.escape(phrase) for phrase, _ in ordered)
        pattern = re.compile(
            rf"^\s*(?P<phrase>{alternatives})(?![{cls._WORD_CHAR_CLASS}])"
        )
        return pattern, {phrase: rule for phrase, rule in ordered}

    @classmethod
    def _compile_rewrite_rules(
        cls, rules: tuple[RewriteRule, ...]
    ) -> tuple[re.Pattern[str], dict[str, RewriteRule]]:
        ordered = cls._ordered_phrases(rules)
        alternatives = "|".join(re.escape(phrase) for phrase, _ in ordered)
        pattern = re.compile(
            rf"(?<![{cls._WORD_CHAR_CLASS}])(?P<phrase>{alternatives})(?![{cls._WORD_CHAR_CLASS}])"
        )
        return pattern, {phrase: rule for phrase, rule in ordered}

    @staticmethod
    def _ordered_phrases(
        rules: tuple[PrefixRule, ...] | tuple[RewriteRule, ...],
    ) -> list[tuple[str, PrefixRule | RewriteRule]]:
        phrases: list[tuple[str, PrefixRule | RewriteRule, int]] = []
        for rule_index, rule in enumerate(rules):
            for phrase in rule.phrases:
                phrases.append((phrase, rule, rule_index))
        phrases.sort(key=lambda item: (-item[1].priority, -len(item[0]), item[2], item[0]))
        return [(phrase, rule) for phrase, rule, _ in phrases]

    def _remove_polite_prefix(self, value: str) -> tuple[str, list[str]]:
        applied: list[str] = []
        while value:
            match = self._prefix_pattern.match(value)
            if not match:
                break
            phrase = match.group("phrase")
            value = value[match.end() :]
            rule = self._prefix_lookup.get(phrase)
            if rule and rule.name not in applied:
                applied.append(rule.name)
            value = self._strip_boundary_noise(value)
        return value, applied

    def _rewrite_synonyms(self, value: str) -> tuple[str, list[str]]:
        applied: list[str] = []

        def replace(match: Match[str]) -> str:
            phrase = match.group("phrase")
            rule = self._synonym_lookup[phrase]
            if rule.name not in applied:
                applied.append(rule.name)
            return rule.replacement

        return self._synonym_pattern.sub(replace, value), applied

    def _remove_courtesy_suffix(self, value: str) -> str:
        changed = True
        while changed and value:
            changed = False
            for suffix in self._COURTESY_SUFFIXES:
                if value.endswith(suffix):
                    value = self._strip_boundary_noise(value[: -len(suffix)])
                    changed = True
                    break
        return value

    @classmethod
    def _strip_boundary_noise(cls, value: str) -> str:
        start = 0
        end = len(value)
        while start < end and cls._is_boundary_noise(value[start]):
            start += 1
        while end > start and cls._is_boundary_noise(value[end - 1]):
            end -= 1
        return value[start:end]

    @classmethod
    def _is_boundary_noise(cls, value: str) -> bool:
        return value.isspace() or value in cls._LEADING_NOISE or unicodedata.category(value).startswith("P")
