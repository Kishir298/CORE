"""Attachment controller (terminal display over existing DocumentStore).

Documents actually attach via DocumentStore.attach() so they reach the
conversation/context pipeline — never pasted as fake uploads. Images use
a capability gate until the active provider supports vision.
"""

from __future__ import annotations

from pathlib import Path

from asis.documents.store import DocumentStore

IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp"})


def capability_notice(supported: bool) -> str:
    if supported:
        return "Image attachment available for current model."
    return "Image attachment unavailable for current model."


class AttachmentController:
    """Terminal-native [+ ] Attach control around DocumentStore + image gate."""

    def __init__(self, store: DocumentStore | None = None) -> None:
        self.store = store if store is not None else DocumentStore()
        self.images: list[str] = []

    def attach(self, path: str, vision_supported: bool = False) -> str:
        cleaned = (path or "").strip().strip("\"'")
        suffix = Path(cleaned).suffix.lower()
        if suffix in IMAGE_SUFFIXES:
            if not vision_supported:
                return capability_notice(False)
            if not cleaned:
                raise ValueError("no file path provided. Usage: /attach <path>")
            self.images.append(Path(cleaned).name or cleaned)
            return f"attached image: {self.images[-1]}"
        doc = self.store.attach(cleaned)
        return f"attached: {doc.name} ({doc.chars} chars)"

    def remove(self, name: str) -> bool:
        cleaned = (name or "").strip()
        before_docs = len(self.store.list_names())
        self.store._docs = [d for d in self.store._docs if d.name != cleaned]
        before_imgs = len(self.images)
        self.images = [i for i in self.images if i != cleaned]
        return len(self.store.list_names()) != before_docs or len(self.images) != before_imgs

    def clear(self) -> int:
        n = len(self.store.list_names()) + len(self.images)
        self.store.clear()
        self.images.clear()
        return n

    def display(self) -> str:
        names = self.store.list_names() + [f"🖼 {i}" for i in self.images]
        if not names:
            return "Attachments: (none)"
        return "Attachments:\n" + "\n".join(f"📄 {n}" if not n.startswith("🖼") else n for n in names)
