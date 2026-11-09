"""One persistent interactive session (single AssistantApp, shared all modes)."""

from __future__ import annotations

from typing import Any

from asis.documents import DocumentStore, build_document_context


class InteractiveSession:
    """Owns interaction mode + documents around a single AssistantApp."""

    def __init__(
        self, app, pipeline=None, doc_store: DocumentStore | None = None
    ) -> None:
        self.app = app
        self.pipeline = pipeline
        self.docs = doc_store if doc_store is not None else DocumentStore()
        self.interaction_mode = "text"  # text | voice
        self._original_assembler = None
        self._wire_document_context()

    def _wire_document_context(self) -> None:
        """Append bounded doc context to the existing assembler path."""
        original = getattr(self.app, "_assembler_context", None)
        if not callable(original):
            return
        if getattr(original, "_asis_docs_wired", False):
            return
        store = self.docs

        def _combined() -> str:
            try:
                base = original()
            except Exception:
                base = ""
            try:
                # Use the pending user query for lightweight retrieval.
                query = getattr(self.app, "_pending_memory_query", "") or ""
                extra = build_document_context(store, query)
            except Exception:
                extra = ""
            if base and extra:
                return base + "\n\n" + extra
            return extra or base

        _combined._asis_docs_wired = True  # type: ignore[attr-defined]
        self._original_assembler = original
        self.app._assembler_context = _combined  # type: ignore[method-assign]

    def set_interaction_mode(self, mode: str) -> str:
        normalized = (mode or "").strip().lower()
        if normalized not in ("text", "voice"):
            raise ValueError(f"unknown mode: {mode!r} (expected text or voice)")
        self.interaction_mode = normalized
        return normalized

    def toggle_mode(self) -> str:
        self.interaction_mode = "voice" if self.interaction_mode == "text" else "text"
        return self.interaction_mode

    def chat_text(self, message: str) -> str:
        """Text-mode turn through the shared AssistantApp (mockable)."""
        return self.app.chat(message)

    def chat_text_streamed(self, message: str, on_chunk=None) -> str:
        """Text-mode turn with live chunk callback when supported."""
        chat_streamed = getattr(self.app, "chat_streamed", None)
        if callable(chat_streamed):
            return chat_streamed(message, on_chunk=on_chunk)
        return self.app.chat(message)

    def voice_turn(self) -> dict[str, Any]:
        """One voice turn: STT -> app.chat -> TTS (same final text both places).

        Returns ``{transcript, response, status}``.  Raises a clean
        RuntimeError (never raw traceback material) when voice is unavailable.
        """
        if self.pipeline is None:
            raise RuntimeError(
                "voice is unavailable (no audio pipeline). "
                "Use /mode text to keep typing."
            )

        def _process(transcript: str, speaker) -> str:
            known = (
                speaker is not None
                and getattr(speaker, "is_known", False)
                and getattr(speaker, "speaker_id", "unknown") != "unknown"
            )
            if known:
                return self.app.chat(f"[{speaker.speaker_id}] {transcript}")
            return self.app.chat(transcript)

        try:
            result = self.pipeline.run_once(
                process_fn=_process, require_wake_word=False
            )
        except Exception as exc:
            raise RuntimeError(f"voice turn failed: {exc}") from exc
        return {
            "transcript": (result or {}).get("text", ""),
            "response": (result or {}).get("response", ""),
            "status": (result or {}).get("status", ""),
            "raw": result,
        }
