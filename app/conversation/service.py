from datetime import datetime, timedelta, timezone

from app.agent_platform.repository import ConversationRepository
from app.conversation.models import ConversationState, ConversationStateUpdate, ConversationTimeRange, SelectedEntity


class ConversationStateService:
    def __init__(self, repository: ConversationRepository) -> None:
        self.repository = repository

    def get(self, *, tenant_id: str, agent_id: str, requester_id: str, chat_id: str) -> ConversationState:
        row = self.repository.get_state(
            tenant_id=tenant_id, agent_id=agent_id, requester_id=requester_id, chat_id=chat_id,
        )
        if row is None or self._is_expired(row.expires_at):
            return ConversationState(
                tenant_id=tenant_id, agent_id=agent_id, requester_id=requester_id, chat_id=chat_id,
            )
        return ConversationState(
            tenant_id=tenant_id, agent_id=agent_id, requester_id=requester_id, chat_id=chat_id,
            topic=row.topic,
            selected_entity=(SelectedEntity.model_validate(row.selected_entity_json) if row.selected_entity_json else None),
            result_refs=list(row.result_refs_json or []),
            time_range=(ConversationTimeRange.model_validate(row.time_range_json) if row.time_range_json else None),
            version=row.state_version, expires_at=row.expires_at,
        )

    @staticmethod
    def _is_expired(expires_at: datetime | None) -> bool:
        if expires_at is None:
            return False
        comparable = expires_at if expires_at.tzinfo is not None else expires_at.replace(tzinfo=timezone.utc)
        return comparable <= datetime.now(timezone.utc)

    def save(
        self, *, tenant_id: str, agent_id: str, requester_id: str,
        chat_id: str, channel: str, update: ConversationStateUpdate,
    ) -> ConversationState:
        session_row = self.repository.get_or_create_session(
            tenant_id=tenant_id, agent_id=agent_id, requester_id=requester_id,
            chat_id=chat_id, channel=channel,
        )
        self.repository.save_state(
            session_row=session_row, expected_version=update.expected_version,
            topic=update.topic,
            selected_entity_json=(update.selected_entity.model_dump(mode="json") if update.selected_entity else {}),
            result_refs_json=update.result_refs,
            time_range_json=(update.time_range.model_dump(mode="json") if update.time_range else {}),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=update.ttl_seconds),
        )
        return self.get(
            tenant_id=tenant_id, agent_id=agent_id, requester_id=requester_id, chat_id=chat_id,
        )

    def clear(self, *, tenant_id: str, agent_id: str, requester_id: str, chat_id: str) -> None:
        self.repository.clear_state(
            tenant_id=tenant_id, agent_id=agent_id, requester_id=requester_id, chat_id=chat_id,
        )
