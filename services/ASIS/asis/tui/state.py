"""A.S.I.S. TUI shared application state.

Single source of truth for all UI widgets. Widgets read from this state
and never hold local status. All mutations go through explicit methods
or event handlers that update this state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class VoiceState(Enum):
    """Voice pipeline states."""
    IDLE = "IDLE"
    READY = "READY"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    SPEAKING = "SPEAKING"
    ERROR = "ERROR"
    OFF = "OFF"


class InteractionMode(Enum):
    """User interaction modes."""
    TEXT = "TEXT"
    VOICE = "VOICE"


class AssistantMode(Enum):
    """Assistant operation modes."""
    GENERAL = "GENERAL"
    CODING = "CODING"
    TRANSLATION = "TRANSLATION"


@dataclass
class BootLogEntry:
    """Single boot log line."""
    timestamp: datetime
    level: str  # BOOT, OK, FAIL, WARN
    message: str


@dataclass
class ConversationMessage:
    """Single conversation message."""
    timestamp: datetime
    role: str  # "user", "assistant", "tool", "system"
    content: str
    tool_name: str | None = None
    tool_status: str | None = None  # STARTED, RUNNING, DONE, FAIL
    streaming: bool = False


@dataclass
class Attachment:
    """Attached document."""
    name: str
    path: str
    mime_type: str | None = None
    icon: str = "📄"


@dataclass
class PermissionRequest:
    """Pending permission request."""
    capability: str
    tool_name: str
    arguments: dict[str, Any]
    timestamp: datetime


@dataclass
class AppState:
    """Complete application state for the TUI."""

    # Model / runtime
    model_name: str = "qwen3:14b"
    ollama_online: bool = False
    model_ready: bool = False

    # Inference options (from CLI)
    ai_temperature: float | None = None
    ai_think: str | None = None
    ai_num_predict: int | None = None
    ai_keep_alive: str | None = None

    # Provider/Model overrides (from CLI)
    ai_provider_override: str | None = None
    ai_model_override: str | None = None

    # Subsystem readiness
    memory_ready: bool = False
    tools_ready: bool = False
    voice_state: VoiceState = VoiceState.OFF

    # Interaction state
    interaction_mode: InteractionMode = InteractionMode.TEXT
    assistant_mode: AssistantMode = AssistantMode.GENERAL

    # Workspace
    workspace_path: str | None = None

    # Boot log
    boot_log: list[BootLogEntry] = field(default_factory=list)

    # Conversation
    conversation: list[ConversationMessage] = field(default_factory=list)

    # Attachments
    attachments: list[Attachment] = field(default_factory=list)

    # Input state
    input_text: str = ""
    input_multiline: bool = False
    generating: bool = False

    # Permission modal
    permission_request: PermissionRequest | None = None
    permission_modal_open: bool = False

    # Layout state
    left_column_collapsed: bool = False
    left_column_width: int | None = None
    terminal_width: int = 120
    terminal_height: int = 38

    # Shutdown tracking
    shutdown_requested: bool = False

    def add_boot_log(self, level: str, message: str) -> None:
        """Add a boot log entry."""
        self.boot_log.append(BootLogEntry(
            timestamp=datetime.now(),
            level=level.upper(),
            message=message
        ))

    def add_conversation_message(
        self,
        role: str,
        content: str,
        tool_name: str | None = None,
        tool_status: str | None = None,
        streaming: bool = False
    ) -> int:
        """Add a conversation message, return its index."""
        msg = ConversationMessage(
            timestamp=datetime.now(),
            role=role,
            content=content,
            tool_name=tool_name,
            tool_status=tool_status,
            streaming=streaming
        )
        self.conversation.append(msg)
        return len(self.conversation) - 1

    def update_last_message(self, content: str, streaming: bool = False) -> None:
        """Update the last assistant message (for streaming)."""
        for msg in reversed(self.conversation):
            if msg.role == "assistant" and not msg.tool_name:
                msg.content = content
                msg.streaming = streaming
                break

    def set_tool_status(self, tool_name: str, status: str) -> None:
        """Update tool status in conversation."""
        for msg in reversed(self.conversation):
            if msg.tool_name == tool_name:
                msg.tool_status = status
                break

    def add_attachment(self, name: str, path: str, mime_type: str | None = None) -> None:
        """Add an attachment."""
        icon = self._icon_for_mime(mime_type) if mime_type else "📄"
        self.attachments.append(Attachment(name=name, path=path, mime_type=mime_type, icon=icon))

    def remove_attachment(self, name: str) -> bool:
        """Remove an attachment by name."""
        for i, att in enumerate(self.attachments):
            if att.name == name:
                self.attachments.pop(i)
                return True
        return False

    def clear_attachments(self) -> None:
        """Clear all attachments."""
        self.attachments.clear()

    def _icon_for_mime(self, mime_type: str) -> str:
        """Map MIME type to icon."""
        if mime_type.startswith("image/"):
            return "🖼"
        if mime_type == "application/pdf":
            return "📄"
        if mime_type.startswith("text/"):
            return "📝"
        if mime_type in ("application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"):
            return "📄"
        return "📎"

    def set_permission_request(self, capability: str, tool_name: str, arguments: dict[str, Any]) -> None:
        """Set a pending permission request and open modal."""
        self.permission_request = PermissionRequest(
            capability=capability,
            tool_name=tool_name,
            arguments=arguments,
            timestamp=datetime.now()
        )
        self.permission_modal_open = True

    def clear_permission_request(self) -> None:
        """Clear the permission request and close modal."""
        self.permission_request = None
        self.permission_modal_open = False

    def toggle_interaction_mode(self) -> InteractionMode:
        """Toggle between text and voice mode."""
        if self.interaction_mode == InteractionMode.TEXT:
            self.interaction_mode = InteractionMode.VOICE
        else:
            self.interaction_mode = InteractionMode.TEXT
        return self.interaction_mode

    def set_assistant_mode(self, mode: AssistantMode) -> None:
        """Set the assistant mode."""
        self.assistant_mode = mode

    def update_terminal_size(self, width: int, height: int) -> None:
        """Update terminal dimensions and compute layout state."""
        self.terminal_width = width
        self.terminal_height = height
        # Auto-collapse left column below 90 columns
        self.left_column_collapsed = width < 90

    def get_left_column_width(self) -> int:
        """Get left column width in columns."""
        if self.left_column_collapsed:
            return 0
        # Use custom width if set, otherwise calculate from terminal width
        if self.left_column_width is not None and self.left_column_width > 0:
            return min(self.left_column_width, self.terminal_width - 20)
        return max(28, self.terminal_width // 4)

    def get_right_column_width(self) -> int:
        """Get right column width in columns."""
        left = self.get_left_column_width()
        return self.terminal_width - left

    def get_layout_rows(self) -> dict[str, tuple[int, int]]:
        """Get row ranges for each panel (start_row, height)."""
        h = self.terminal_height - 1  # minus status bar
        if h < 10:
            return {}

# Row boundaries as percentages of content height
        r0 = 0
        r1 = max(3, int(h * 0.11))      # Identity / Header (11%)
        r2 = max(r1 + 1, int(h * 0.29))  # Status (18%)
        r3 = max(r2 + 1, int(h * 0.61))  # Boot log / Conversation (32%)
        r4 = max(r3 + 1, int(h * 0.96))  # Mode footer (35%)

        return {
            "identity": (r0, r1 - r0),
            "status": (r1, r2 - r1),
            "boot_log": (r2, r3 - r2),
            "mode_footer": (r3, r4 - r3),
            "header": (r0, r1 - r0),
            "conversation": (r1, r3 - r1),
            "attachments": (r3, 1),
            "input_box": (r3 + 1, max(3, int(h * 0.20))),
            "voice_bar": (r4 - 2, 2),
            "status_bar": (h, 1),
        }
