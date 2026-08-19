import re
from dataclasses import dataclass

from app.agent_platform.search import normalize_dialogue_query, tokenize
from app.conversation.models import ConversationState


@dataclass(frozen=True)
class SelectedContext:
    text: str
    selected_message_ids: tuple[int, ...]
    omitted_sensitive_count: int
    truncated: bool


class ConversationContextSelector:
    """Select minimal relevant context; never forwards secret-classified messages."""

    allowed_roles = {"user", "assistant"}
    blocked_sensitivity = {"secret", "restricted"}
    _secret_patterns = (
        re.compile(
            r"(?i)(?<![A-Za-z0-9_])bearer\s+"
            r"[A-Za-z0-9._~+/-]{8,}(?![A-Za-z0-9._~-])"
        ),
        re.compile(
            r"(?i)(?<![A-Za-z0-9_])"
            r"(?:api[\s_-]*key|access[\s_-]*token|refresh[\s_-]*token|"
            r"client[\s_-]*secret|private[\s_-]*key|password|passwd|secret|token|"
            r"authorization)"
            r"(?![A-Za-z0-9_])\s*(?:[:=：]\s*)"
            r"(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|`[^`\r\n]*`|[^\s,;，；。]+)"
        ),
        re.compile(
            r"(?<![A-Za-z0-9_])(?:sk-[A-Za-z0-9]{12,}|"
            r"gh[pousr]_[A-Za-z0-9_]{12,}|xox[baprs]-[A-Za-z0-9-]{12,}|"
            r"AIza[A-Za-z0-9_-]{20,})(?![A-Za-z0-9_-])"
        ),
    )

    def __init__(self, *, max_chars: int = 4000, max_messages: int = 8) -> None:
        self.max_chars = max_chars
        self.max_messages = max_messages

    def select(self, *, query: str, messages: list, state: ConversationState) -> SelectedContext:
        query_terms = set(tokenize(normalize_dialogue_query(query)))
        safe = []
        omitted_sensitive = 0
        for position, message in enumerate(messages):
            if message.role not in self.allowed_roles:
                continue
            if message.content_redacted or message.sensitivity in self.blocked_sensitivity:
                omitted_sensitive += 1
                continue
            content = self._redact_inline_secrets(getattr(message, "content", None))
            if not content:
                continue
            terms = set(tokenize(content))
            overlap = len(query_terms.intersection(terms))
            recency = position / max(len(messages), 1)
            # Preserve the newest exchange for pronoun/ellipsis follow-ups.
            is_recent = position >= max(0, len(messages) - 2)
            if overlap == 0 and not is_recent:
                continue
            score = overlap * 10 + recency + (5 if is_recent else 0)
            safe.append((score, position, message, content))

        selected = sorted(safe, key=lambda item: (-item[0], -item[1]))[: self.max_messages]
        selected.sort(key=lambda item: item[1])
        blocks = []
        if state.version > 0:
            blocks.append(self._format_state(state))
        ids = []
        truncated = False
        used = sum(len(block) for block in blocks) + max(0, len(blocks) - 1)
        for _, _, message, content in selected:
            prefix = "用户" if message.role == "user" else "助手"
            block = f"{prefix}：{content.strip()}"
            separator_cost = 1 if blocks else 0
            remaining = self.max_chars - used - separator_cost
            if remaining <= len(prefix) + 2:
                truncated = True
                break
            if len(block) > remaining:
                block = block[: max(0, remaining - 1)] + "…"
                truncated = True
            blocks.append(block)
            ids.append(message.id)
            used += separator_cost + len(block)
            if truncated:
                break
        return SelectedContext("\n".join(blocks), tuple(ids), omitted_sensitive, truncated)

    @staticmethod
    def _format_state(state: ConversationState) -> str:
        parts = [f"当前主题：{state.topic or '-'}"]
        if state.selected_entity:
            parts.append(
                f"当前对象：{state.selected_entity.entity_type}/{state.selected_entity.entity_id}"
            )
        if state.result_refs:
            parts.append("上一轮结果：" + "、".join(state.result_refs))
        if state.time_range:
            parts.append(
                f"时间范围：{state.time_range.start or '-'} 至 {state.time_range.end or '-'}"
            )
        return "【结构化会话状态】\n" + "\n".join(parts)

    @classmethod
    def _redact_inline_secrets(cls, content: object) -> str:
        if not isinstance(content, str):
            return ""
        redacted = content
        for pattern in cls._secret_patterns:
            redacted = pattern.sub("[敏感信息已隐藏]", redacted)
        return redacted
