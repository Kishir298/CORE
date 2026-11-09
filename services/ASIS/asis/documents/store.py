"""Session-scoped attached-document state."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .parsers import parse_file

MAX_DOCS = 10
MAX_CHARS_PER_DOC_IN_CONTEXT = 4_000
MAX_TOTAL_CONTEXT_CHARS = 12_000


@dataclass
class AttachedDocument:
    name: str
    path: str
    text: str
    chars: int = field(init=False)

    def __post_init__(self) -> None:
        self.chars = len(self.text)


class DocumentStore:
    """Tracks documents attached to the current conversation session."""

    def __init__(self) -> None:
        self._docs: list[AttachedDocument] = []

    def __len__(self) -> int:
        return len(self._docs)

    def attach(self, path: str | Path) -> AttachedDocument:
        cleaned = str(path).strip().strip("\"'")
        if not cleaned:
            raise ValueError("no file path provided. Usage: /upload <path>")
        if len(self._docs) >= MAX_DOCS:
            raise ValueError(f"too many attached documents (max {MAX_DOCS}).")
        text = parse_file(cleaned)
        name = Path(cleaned).name or cleaned
        doc = AttachedDocument(name=name, path=cleaned, text=text)
        # Replace same-name re-uploads instead of duplicating.
        self._docs = [d for d in self._docs if d.name != name]
        self._docs.append(doc)
        return doc

    def list_docs(self) -> list[AttachedDocument]:
        return list(self._docs)

    def list_names(self) -> list[str]:
        return [d.name for d in self._docs]

    def clear(self) -> int:
        count = len(self._docs)
        self._docs.clear()
        return count

    def detach(self, name: str) -> bool:
        """Remove one attached document by name; True when something changed."""
        cleaned = (name or "").strip()
        kept = [d for d in self._docs if d.name != cleaned]
        changed = len(kept) != len(self._docs)
        self._docs = kept
        return changed
