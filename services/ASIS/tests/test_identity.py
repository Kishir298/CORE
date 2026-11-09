"""Tests for the identity subsystem."""

from __future__ import annotations

from asis.identity import Identity, build_identity


def test_system_prompt_formatting():
    identity = Identity(
        name="ASIS",
        title="the assistant",
        personality="Be kind.",
    )
    prompt = identity.system_prompt()

    assert "You are ASIS, the assistant." in prompt
    assert "Be kind." in prompt


def test_build_identity_from_settings():
    identity = build_identity()
    assert identity.name
    assert identity.title
    assert identity.personality
    assert identity.greeting


def test_build_identity_renders_personality_template():
    identity = build_identity(personality_text="Serve as {name}, a helper.")
    assert "{name}" not in identity.personality
    assert "helper" in identity.personality
    assert "Serve as" in identity.personality


def test_build_identity_defaults_preferences():
    identity = build_identity()
    assert identity.preferences == {}


def test_identity_is_frozen():
    identity = Identity(name="N", title="T", personality="P")
    try:
        identity.name = "other"
    except Exception as exc:
        assert isinstance(exc, (AttributeError, TypeError))
    else:
        raise AssertionError("frozen dataclass allowed mutation")
