"""Display tests: attachments reach DocumentStore + image capability gate."""

from __future__ import annotations

import pytest

from asis.ai.models import AIMessage, MessageRole
from asis.ai.providers.mock import MockAIProvider
from asis.cli.terminal.attachments import AttachmentController, capability_notice


def test_attach_real_doc_reaches_store(tmp_path):
    c = AttachmentController()
    f = tmp_path / "physics_notes.pdf"
    f.write_bytes(b"%PDF-1.4 fake")
    msg = c.attach(str(f))
    assert "attached:" in msg and f.name in c.store.list_names()
    assert f.name in c.display()
    assert c.remove(f.name) is True
    assert "(none)" in c.display()


def test_attach_unsupported_and_invalid(tmp_path):
    c = AttachmentController()
    exe = tmp_path / "x.exe"
    exe.write_bytes(b"MZ")
    with pytest.raises(ValueError):
        c.attach(str(exe))
    assert "unavailable" in c.attach("photo.png", vision_supported=False)
    assert "available" in capability_notice(True)
    assert c.attach("pic.png", vision_supported=True).startswith("attached image")
    assert c.clear() >= 1


def test_multimodal_contract_defaults():
    m = AIMessage(role=MessageRole.USER, content="hi")
    assert m.attachments == ()
    p = MockAIProvider()
    assert p.supports_vision is False
    m2 = AIMessage(role=MessageRole.USER, content="see", attachments=({"type": "image", "name": "a.png"},))
    assert m2.attachments[0]["name"] == "a.png"
