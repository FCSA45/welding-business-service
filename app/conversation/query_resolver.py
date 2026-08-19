import logging
import re
from dataclasses import dataclass
from typing import Literal

from app.agent_platform.search import normalize_dialogue_query, tokenize
from app.conversation.models import ConversationState


logger = logging.getLogger(__name__)
ResolutionStatus = Literal["unchanged", "resolved", "needs_clarification"]


@dataclass(frozen=True)
class QueryResolution:
    original_query: str
    resolved_query: str
    status: ResolutionStatus
    confidence: float
    entity_ref: str | None = None
    reason: str = ""
    clarification: str | None = None


class ConversationQueryResolver:
    """Deterministic coreference resolution; ambiguous references are never guessed."""

    _ordinal_words = {
        "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
        "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    }
    _reference_terms = ("它", "他", "她", "这个", "那个", "该项", "刚才那个", "上面那个", "这个单", "这条")
    _reference_pattern = re.compile(
        r"(?<![A-Za-z0-9_])(?:刚才那个|上面那个|这个单|这个|那个|该项|这条|"
        r"它(?!们)|他(?!们|人)|她(?!们))(?![A-Za-z0-9_])"
    )
    _standalone_business_terms = {
        "工单", "设备", "报警", "库存", "绩效", "报表", "订单", "异常", "延期",
        "负责人", "交期", "产量", "完成率", "部门", "客户", "商品",
    }

    def resolve(
        self, *, query: str, state: ConversationState,
        tenant_id: str, agent_id: str, requester_id: str, chat_id: str,
    ) -> QueryResolution:
        safe_query = query if isinstance(query, str) else ""
        try:
            return self._resolve(
                query=safe_query,
                state=state,
                tenant_id=tenant_id,
                agent_id=agent_id,
                requester_id=requester_id,
                chat_id=chat_id,
            )
        except Exception:
            logger.exception("Conversation query resolution failed")
            return self._clarify(
                safe_query[:12000],
                "query_processing_failed",
                "当前问题无法安全解析，请补充对象编号或名称。",
            )

    def _resolve(
        self, *, query: str, state: ConversationState,
        tenant_id: str, agent_id: str, requester_id: str, chat_id: str,
    ) -> QueryResolution:
        original = normalize_dialogue_query(query)
        if len(original) > 12000:
            return self._clarify(original, "query_too_long", "问题过长，请缩短后重新提问。")
        if not self._same_scope(state, tenant_id, agent_id, requester_id, chat_id):
            return self._clarify(original, "state_scope_mismatch", "当前会话状态无效，请重新说明要查询的对象。")

        result_refs = state.result_refs if isinstance(state.result_refs, list) else []
        selected_entity = state.selected_entity
        if self._is_self_contained(original):
            return QueryResolution(original, original, "unchanged", 1.0, reason="self_contained")

        ordinal = self._ordinal(original)
        if ordinal is not None:
            if ordinal < 1 or ordinal > len(result_refs):
                return self._clarify(
                    original, "ordinal_out_of_range",
                    f"上一轮只有 {len(result_refs)} 个结果，请重新选择。",
                )
            entity_ref = result_refs[ordinal - 1]
            if not isinstance(entity_ref, str) or not self._safe_ref(entity_ref):
                return self._clarify(original, "unsafe_entity_ref", "上一轮对象标识无效，请重新查询。")
            resolved = self._replace_ordinal(original, entity_ref)
            return QueryResolution(original, resolved, "resolved", 1.0, entity_ref, "ordinal_reference")

        if self._has_reference(original):
            entity_ref = None
            if selected_entity is not None:
                candidate = getattr(selected_entity, "entity_id", None)
                entity_ref = candidate if isinstance(candidate, str) else None
            if entity_ref is None:
                if len(result_refs) == 1 and isinstance(result_refs[0], str) and self._safe_ref(result_refs[0]):
                    entity_ref = result_refs[0]
                else:
                    return self._clarify(
                        original, "ambiguous_reference",
                        "无法确定你指的是哪个对象，请提供对象编号或名称。",
                    )
            if not self._safe_ref(entity_ref):
                return self._clarify(original, "unsafe_entity_ref", "当前对象标识无效，请重新指定。")
            resolved = self._replace_references(original, entity_ref)
            return QueryResolution(original, resolved, "resolved", 0.95, entity_ref, "pronoun_reference")

        if selected_entity is not None and len(tokenize(original)) <= 4:
            entity_ref = getattr(selected_entity, "entity_id", None)
            if not isinstance(entity_ref, str) or not self._safe_ref(entity_ref):
                return self._clarify(original, "unsafe_entity_ref", "当前对象标识无效，请重新指定。")
            return QueryResolution(
                original, f"关于 {entity_ref}：{original}", "resolved", 0.85,
                entity_ref, "elliptical_follow_up",
            )
        return self._clarify(original, "insufficient_context", "问题缺少明确对象，请补充编号或名称。")

    def _is_self_contained(self, query: str) -> bool:
        if self._has_reference(query) or self._ordinal(query) is not None:
            return False
        terms = set(tokenize(query))
        if terms.intersection(self._standalone_business_terms):
            return True
        return bool(re.search(r"\b[A-Za-z]{1,12}[-_][A-Za-z0-9_-]{1,100}\b", query))

    @classmethod
    def _ordinal(cls, query: str) -> int | None:
        match = re.search(r"第\s*(\d{1,2}|[一二三四五六七八九十])\s*(?:个|条|项|张|笔|台|单)?", query)
        if not match:
            return None
        raw = match.group(1)
        return int(raw) if raw.isdigit() else cls._ordinal_words.get(raw)

    @staticmethod
    def _replace_ordinal(query: str, entity_ref: str) -> str:
        return re.sub(
            r"第\s*(?:\d{1,2}|[一二三四五六七八九十])\s*(?:个|条|项|张|笔|台|单)?",
            entity_ref, query, count=1,
        )

    @classmethod
    def _has_reference(cls, query: str) -> bool:
        return cls._reference_pattern.search(query) is not None

    @classmethod
    def _replace_references(cls, query: str, entity_ref: str) -> str:
        return cls._reference_pattern.sub(entity_ref, query)

    @staticmethod
    def _safe_ref(value: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}", value))

    @staticmethod
    def _same_scope(state, tenant_id, agent_id, requester_id, chat_id) -> bool:
        return (
            state.tenant_id == tenant_id and state.agent_id == agent_id
            and state.requester_id == requester_id and state.chat_id == chat_id
        )

    @staticmethod
    def _clarify(query: str, reason: str, message: str) -> QueryResolution:
        return QueryResolution(query, query, "needs_clarification", 0.0, reason=reason, clarification=message)
