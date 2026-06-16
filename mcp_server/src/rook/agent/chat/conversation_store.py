"""ConversationStore — manages conversation lifecycle."""
import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Conversation:
    """A single active conversation with an agent persona."""
    id: str
    persona: str
    document_serial_number: int = 0
    model: str = ""
    api_base: str = ""                     # For local providers (LM Studio, vLLM, Ollama)
    model_source: str = ""
    api_base_source: str = ""
    pending_model: str = ""
    pending_api_base: str = ""
    pending_model_source: str = ""
    pending_api_base_source: str = ""
    pending_model_reason: str = ""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    abort_event: asyncio.Event = field(default_factory=asyncio.Event)
    active_run_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

    def touch(self):
        """Update last activity timestamp."""
        self.last_activity = time.time()

    def _model_payload(
        self,
        *,
        active: bool,
        applies_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        prefix = "active" if active else "pending"
        model = self.model if active else self.pending_model
        api_base = self.api_base if active else self.pending_api_base
        model_source = self.model_source if active else self.pending_model_source
        api_base_source = (
            self.api_base_source if active else self.pending_api_base_source
        )
        routing = (
            "local"
            if api_base or model.startswith(("ollama_chat/", "ollama/"))
            else "cloud"
        )
        payload: Dict[str, Any] = {
            f"{prefix}_model": model,
            f"{prefix}_routing": routing,
            "model_source": model_source,
            "api_base_source": api_base_source,
        }
        if applies_to:
            payload["applies_to"] = applies_to
        return payload

    def apply_model_override(
        self,
        resolution: Any,
        *,
        source: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        """Atomically apply an active model/api_base pair."""
        self.model = resolution.model_override
        self.api_base = resolution.api_base
        self.model_source = source
        self.api_base_source = resolution.api_base_source
        self.pending_model = ""
        self.pending_api_base = ""
        self.pending_model_source = ""
        self.pending_api_base_source = ""
        self.pending_model_reason = ""
        self.touch()
        return self._model_payload(active=True)

    def stage_model_override(
        self,
        resolution: Any,
        *,
        source: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        """Stage a model/api_base pair for the next turn."""
        self.pending_model = resolution.model_override
        self.pending_api_base = resolution.api_base
        self.pending_model_source = source
        self.pending_api_base_source = resolution.api_base_source
        self.pending_model_reason = reason
        self.touch()
        return self._model_payload(active=False, applies_to="next_turn")

    def apply_pending_model_override(self) -> Optional[Dict[str, Any]]:
        """Promote a staged model/api_base pair to active, if present."""
        if not self.pending_model:
            return None
        self.model = self.pending_model
        self.api_base = self.pending_api_base
        self.model_source = self.pending_model_source
        self.api_base_source = self.pending_api_base_source
        self.pending_model = ""
        self.pending_api_base = ""
        self.pending_model_source = ""
        self.pending_api_base_source = ""
        self.pending_model_reason = ""
        self.touch()
        return self._model_payload(active=True)


class ConversationStore:
    """In-memory store for active conversations."""

    def __init__(self, max_conversations: int = 10, idle_timeout: float = 1800.0):
        self._conversations: Dict[str, Conversation] = {}
        self._max_conversations = max_conversations
        self._idle_timeout = idle_timeout

    def create(self, persona: str, document_serial_number: int = 0) -> Conversation:
        """Create a new conversation. Raises RuntimeError if at capacity."""
        self._cleanup_idle()
        if len(self._conversations) >= self._max_conversations:
            raise RuntimeError(f"Max conversations ({self._max_conversations}) reached")

        conv_id = f"conv_{uuid.uuid4().hex[:12]}"
        conv = Conversation(
            id=conv_id,
            persona=persona,
            document_serial_number=document_serial_number,
        )
        self._conversations[conv_id] = conv
        logger.info(f"Created conversation {conv_id} with persona '{persona}'")
        return conv

    def get(self, conversation_id: str) -> Optional[Conversation]:
        """Get a conversation by ID, or None if not found."""
        return self._conversations.get(conversation_id)

    def stop(self, conversation_id: str) -> bool:
        """Stop and remove a conversation. Returns True if found."""
        conv = self._conversations.pop(conversation_id, None)
        if conv:
            conv.abort_event.set()
            logger.info(f"Stopped conversation {conversation_id}")
            return True
        return False

    def list_conversations(self) -> List[Dict[str, Any]]:
        """List all active conversations as dicts."""
        return [
            {
                "id": c.id,
                "persona": c.persona,
                "document_serial_number": c.document_serial_number,
                "model": c.model,
                "api_base_source": c.api_base_source,
                "pending_model": c.pending_model or None,
                "pending_api_base_source": c.pending_api_base_source or None,
                "created_at": c.created_at,
                "last_activity": c.last_activity,
                "message_count": len(c.messages),
            }
            for c in self._conversations.values()
        ]

    def _cleanup_idle(self):
        """Remove conversations idle longer than timeout."""
        now = time.time()
        expired = [
            cid for cid, c in self._conversations.items()
            if now - c.last_activity > self._idle_timeout
        ]
        for cid in expired:
            self.stop(cid)
            logger.info(f"Cleaned up idle conversation {cid}")
