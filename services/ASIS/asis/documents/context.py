"""Bounded document context for LLM prompts (offline, local only)."""

from __future__ import annotations

from .store import (
    MAX_CHARS_PER_DOC_IN_CONTEXT,
    MAX_TOTAL_CONTEXT_CHARS,
    DocumentStore,
)

_STOPWORDS = frozenset(
    {
        "what", "when", "where", "which", "who", "whom", "whose", "why", "how",
        "is", "are", "was", "were", "be", "been", "the", "a", "an", "and",
        "or", "of", "to", "in", "on", "for", "with", "about", "this", "that",
        "does", "do", "did", "it", "its", "document", "summarize", "summary",
        "tell", "me", "please", "you",
    }
)


def _keywords(query: str) -> set[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in query)
    flat: set[str] = set()
    for word in cleaned.split():
        if len(word) >= 3 and word not in _STOPWORDS:
            flat.add(word)
    return flat


def build_document_context(store: DocumentStore, query: str = "") -> str:
    """Build a bounded ``ATTACHED DOCUMENTS`` prompt section.

    Document -> normalized text -> chunk/bound -> retrieval -> LLM.
    Empty string when no documents are attached.
    """
    docs = store.list_docs()
    if not docs:
        return ""
    keywords = _keywords(query or "")
    sections: list[str] = []
    used = 0
    for doc in docs:
        text = doc.text.strip()
        if not text:
            continue
        if keywords:
            # Cheap retrieval: paragraphs containing query keywords first.
            paras = [p.strip() for p in text.split("\n\n") if p.strip()]
            ranked = sorted(
                paras,
                key=lambda p: sum(1 for kw in keywords if kw in p.lower()),
                reverse=True,
            )
            ordered = "\n\n".join(ranked)[:MAX_CHARS_PER_DOC_IN_CONTEXT]
        else:
            ordered = text[:MAX_CHARS_PER_DOC_IN_CONTEXT]
        chunk = ordered.strip()
        if not chunk:
            continue
        section = f"--- document: {doc.name} ---\n{chunk}"
        if used + len(section) > MAX_TOTAL_CONTEXT_CHARS:
            remaining = MAX_TOTAL_CONTEXT_CHARS - used
            if remaining < 200:
                break
            section = section[:remaining]
        sections.append(section)
        used += len(section)
        if used >= MAX_TOTAL_CONTEXT_CHARS:
            break
    if not sections:
        return ""
    return "ATTACHED DOCUMENTS:\n" + "\n\n".join(sections)
