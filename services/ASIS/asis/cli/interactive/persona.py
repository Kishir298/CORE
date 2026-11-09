"""Persona-mode console: simulate reconstructed identities over the provider.

Turns in persona mode are routed through the identity record (system prompt
from the stored persona + mode routing) and stream back exactly like a normal
turn. Listing/selection is deterministic and LLM-bypassed; the live provider
is used **only** to generate the persona's reply. The simulated conversation
lives in its own session so it never pollutes normal memory/history, and a
one-time privacy notice is shown (AI reconstruction, never the real person).
"""

from __future__ import annotations

from pathlib import Path

from asis.ai.models import AIMessage, MessageRole
from asis.identities.model import IdentityRecord
from asis.identities.persona import (
    build_persona,
    persona_mode,
    render_persona_prompt,
)
from asis.identities.store import IdentityStore

PRIVACY_NOTICE = (
    "AI reconstruction, not the actual person. Use freely but never "
    "as ground truth about them."
)


class PersonaConsole:
    """Active multi-person identity sim over a single ``AssistantApp``."""

    def __init__(self, app, db_path: str | Path | None = None) -> None:
        self.app = app
        self.db_path = Path(db_path) if db_path else None
        self._store: IdentityStore | None = None
        self._active: IdentityRecord | None = None
        self._seen_notice = False
        self._session: list[AIMessage] = []

    def _store_provider(self) -> IdentityStore:
        if self._store is None:
            if self.db_path is None:
                from asis.configuration.settings import settings as s

                self.db_path = Path(s.paths.memory) / "identities.db"
            self._store = IdentityStore(self.db_path)
        return self._store

    # -- listing / selection -------------------------------------------------

    def names(self) -> list[str]:
        return sorted(i.display_name for i in self._store_provider().list_all())

    def active(self) -> str | None:
        return self._active.display_name if self._active is not None else None

    def enter(self, name: str) -> str:
        """Switch persona mode to ``name``; raises KeyError when unknown."""
        for ident in self._store_provider().list_all():
            if ident.display_name.lower() == name.lower() or ident.identity_id == name:
                self._active = ident
                persona = build_persona(ident)
                self._session = [
                    AIMessage(
                        role=MessageRole.SYSTEM,
                        content=render_persona_prompt(persona, persona_mode(persona, "hello")),
                    )
                ]
                self._seen_notice = False
                return ident.display_name
        raise KeyError(name)

    def exit(self) -> str | None:
        name = self.active()
        self._active = None
        self._session = []
        return name

    def notice(self) -> str | None:
        """Return the privacy notice exactly once per persona session."""
        if self._seen_notice or self._active is None:
            return None
        self._seen_notice = True
        return PRIVACY_NOTICE

    # -- chat ------------------------------------------------------------------

    def _provider(self):
        return getattr(getattr(self.app, "ai", None), "provider", None)

    def chat(self, message: str, on_chunk=None) -> str:
        """Generate the persona's reply (streamed when supported/fresh system)."""
        if self._active is None:
            raise RuntimeError("No active persona. Use /persona <name> first.")
        provider = self._provider()
        if provider is None:
            raise RuntimeError("No AI provider available for persona simulation.")
        text = (message or "").strip()
        if not text:
            return ""
        persona = build_persona(self._active)
        mode = persona_mode(persona, text)
        # Mode change regenerates the system prompt for this turn.
        self._session[0] = AIMessage(
            role=MessageRole.SYSTEM,
            content=render_persona_prompt(persona, mode),
        )
        self._session.append(AIMessage(role=MessageRole.USER, content=text))
        reply = self._stream(provider, self._session, on_chunk) if on_chunk else self._plain(provider, self._session)
        self._session.append(AIMessage(role=MessageRole.ASSISTANT, content=reply or ""))
        return reply or ""

    def _plain(self, provider, messages: list[AIMessage]) -> str:
        response = provider.chat(messages)
        content = getattr(response, "content", "")
        return content if isinstance(content, str) else str(content or "")

    def _stream(self, provider, messages: list[AIMessage], on_chunk) -> str:
        chunker = getattr(provider, "stream_chat", None)
        if not callable(chunker):
            return self._plain(provider, messages)
        parts: list[str] = []
        try:
            for chunk in chunker(messages):
                if chunk:
                    parts.append(chunk)
                    on_chunk(chunk)
        except Exception:
            # Provider streaming edge cases fall back to a plain call so the
            # console never dead-ends on a partial stream.
            return self._plain(provider, messages)
        return "".join(parts)
