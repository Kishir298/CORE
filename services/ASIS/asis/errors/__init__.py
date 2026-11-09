"""
Structured exceptions for A.S.I.S.

Low-level errors must not leak into the public API of the system.
Every subsystem raises a dedicated A.S.I.S. exception instead.
"""

from __future__ import annotations


class ASISError(Exception):
    """Base class for every A.S.I.S. error."""


class ConfigurationError(ASISError):
    """Raised when A.S.I.S. configuration is invalid or missing."""


class ModelError(ASISError):
    """Raised when an AI model provider fails."""


class InferenceError(ModelError):
    """Raised when the inference pipeline fails."""


class ConversationError(ASISError):
    """Raised when a conversation operation fails."""


class ToolError(ASISError):
    """Base class for tool-related errors."""


class ToolValidationError(ToolError):
    """Raised when tool input fails schema validation."""


class ToolNotFoundError(ToolError):
    """Raised when an unregistered tool is requested."""


class PermissionError(ASISError):
    """Raised when a permission check denies an operation.

    This intentionally shadows the builtin ``PermissionError`` inside
    the A.S.I.S. hierarchy so a single error type can be caught as
    ``ASISError`` while still carrying permission semantics.
    """


class VoiceError(ASISError):
    """Base class for voice pipeline errors."""


class SpeechRecognitionError(VoiceError):
    """Raised when speech-to-text fails."""


class SpeakerRecognitionError(VoiceError):
    """Raised when speaker identification fails."""


class TTSError(VoiceError):
    """Raised when text-to-speech fails."""


class MemoryError(ASISError):
    """Raised when a memory operation fails."""


class CancellationError(ASISError):
    """Raised when an operation is cancelled by the interrupt coordinator."""
