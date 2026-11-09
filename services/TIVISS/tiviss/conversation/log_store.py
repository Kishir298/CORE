"""ConversationLogStore for T.I.V.I.S.S. with RESCS namespace integration."""

from __future__ import annotations

import time
import uuid
from typing import Optional, List

from ..memory.sqlite import ConversationLogEntry


DEFAULT_NAMESPACE_PREFIX = "tiviss"
CHAT_LOGS_NAMESPACE = "chat_logs"


def _build_chat_logs_namespace(session_id: str) -> str:
    """Build the RESCS namespace for chat logs."""
    return f"{DEFAULT_NAMESPACE_PREFIX}.{CHAT_LOGS_NAMESPACE}.{session_id}"


class ConversationLogStore:
    """Conversation log store with RESCS namespace integration."""

    def __init__(self, session_id: str, memory_store=None):
        self.session_id = session_id
        self.namespace = _build_chat_logs_namespace(session_id)
        self.memory_store = memory_store
        self._local_entries: List[ConversationLogEntry] = []

    def append(self, request_content: str, response_content: str, metadata: Optional[dict] = None) -> str:
        """Append a conversation exchange to the log."""
        request_id = str(uuid.uuid4())
        if self.memory_store:
            self.memory_store.append_conversation(request_id, request_content, response_content, metadata)
        else:
            self._local_entries.append(ConversationLogEntry(
                log_id=len(self._local_entries) + 1,
                request_id=request_id,
                request_content=request_content,
                response_content=response_content,
                metadata=metadata or {},
                created_at=time.time()
            ))
        return request_id

    def get_history(self, limit: int = 100) -> List[ConversationLogEntry]:
        """Get conversation history for this session."""
        if self.memory_store:
            return self.memory_store.get_conversation_history(limit=limit, session_id=self.session_id)
        return self._local_entries[-limit:]

    def search(self, query: str, limit: int = 10) -> List[ConversationLogEntry]:
        """Search conversation history."""
        if self.memory_store:
            return self.memory_store.search_conversation(query, limit)
        return [e for e in self._local_entries if query in e.request_content or query in e.response_content][:limit]

    def get_namespace(self) -> str:
        """Return the RESCS namespace for this conversation log."""
        return self.namespace

    def clear(self) -> None:
        """Clear local entries (does not clear RESCS store)."""
        self._local_entries.clear()
