from .providers import AudioFrame, SpeechInput, SpeechOutput, Transcriber, Transcript, Vocalizer, VoiceError
from .mock import MockSpeechInput, MockSpeechOutput, MockTranscriber, MockVocalizer
from .pipeline import VoicePipeline, ListenResult, SpeakResult, StatusResult, build_voice_pipeline

def voice_turn(
    agent,
    *, 
    speech_input: "SpeechInput",
    transcriber: "Transcriber",
    vocalizer: "Vocalizer",
    speech_output: "SpeechOutput",
    max_turns: int = 10
) -> str:
    """Run a single voice interaction turn."""
    for _ in range(max_turns):
        frame = speech_input.listen()
        transcript = transcriber.transcribe(frame)
        if not transcript.text:
            raise VoiceError("empty transcription")
        reply = agent(transcript.text, source="voice")
        audio = vocalizer.vocalize(reply.content)
        speech_output.play(audio)
        return reply.content

__all__ = [
    "AudioFrame",
    "SpeechInput",
    "SpeechOutput",
    "Transcriber",
    "Transcript",
    "Vocalizer",
    "VoiceError",
    "MockSpeechInput",
    "MockSpeechOutput",
    "MockTranscriber",
    "MockVocalizer",
    "VoicePipeline",
    "ListenResult",
    "SpeakResult",
    "StatusResult",
    "build_voice_pipeline",
    "voice_turn",
]
