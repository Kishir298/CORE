import pytest

from tiviss.identity import Ownership
from tiviss.models import MockProvider
from tiviss.models.provider import ProviderError
from tiviss.voice import (
    AudioFrame,
    MockSpeechInput,
    MockSpeechOutput,
    MockTranscriber,
    MockVocalizer,
    VoiceError,
    voice_turn,
)


def test_revoke_records_reason():
    ownership = Ownership.create("kishir")
    ownership.revoke(reason="lost device")
    assert ownership.note == "lost device"


def test_provider_timeout_validation():
    provider = MockProvider()
    for bad in (0, -1, float("nan"), float("inf"), "5", True):
        with pytest.raises(ProviderError):
            provider.generate("hi", timeout_s=bad)
    response = provider.generate("hi", timeout_s=30)
    assert response.content


def test_voice_turn_happy_path():
    heard = []

    def fake_agent(text, *, source="voice"):
        heard.append((text, source))

        class Reply:
            content = "reply-text"

        return Reply()

    speech_in = MockSpeechInput([AudioFrame(samples=(0.1, 0.2))])
    transcriber = MockTranscriber(default_text="hello agent")
    vocalizer = MockVocalizer()
    speech_out = MockSpeechOutput()
    result = voice_turn(
        fake_agent,
        speech_input=speech_in,
        transcriber=transcriber,
        vocalizer=vocalizer,
        speech_output=speech_out,
    )
    assert result == "reply-text"
    assert heard == [("hello agent", "voice")]
    assert vocalizer.calls == ["reply-text"]
    assert len(speech_out.played) == 1


def test_voice_turn_empty_input_fails():
    def fake_agent(text, *, source="voice"):
        raise AssertionError("must not be called")

    with pytest.raises(VoiceError):
        voice_turn(
            fake_agent,
            speech_input=MockSpeechInput(),
            transcriber=MockTranscriber(default_text="x"),
            vocalizer=MockVocalizer(),
            speech_output=MockSpeechOutput(),
        )


def test_voice_turn_empty_transcript_fails():
    def fake_agent(text, *, source="voice"):
        raise AssertionError("must not be called")

    with pytest.raises(VoiceError, match="transcribe|empty"):
        voice_turn(
            fake_agent,
            speech_input=MockSpeechInput([AudioFrame()]),
            transcriber=MockTranscriber(default_text=""),
            vocalizer=MockVocalizer(),
            speech_output=MockSpeechOutput(),
        )


def test_voice_timeout_validation():
    with pytest.raises(VoiceError):
        MockSpeechInput([AudioFrame()]).listen(timeout_s=-1)
    with pytest.raises(VoiceError):
        MockVocalizer().vocalize("hi", timeout_s=0)


def test_voice_output_failure_surfaces():
    def fake_agent(text, *, source="voice"):
        class Reply:
            content = "ok"

        return Reply()

    with pytest.raises(VoiceError, match="unavailable"):
        voice_turn(
            fake_agent,
            speech_input=MockSpeechInput([AudioFrame()]),
            transcriber=MockTranscriber(default_text="hi"),
            vocalizer=MockVocalizer(),
            speech_output=MockSpeechOutput(fail=True),
        )
