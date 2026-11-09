"""Conversation Panel - Right column main area.

Scrollable message history with streaming support.
Formats: You >, A.S.I.S. >, [TOOL], [RUN ], [....], [DONE], [FAIL]
"""

from __future__ import annotations

from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Input, RichLog

from asis.tui.state import AppState, ConversationMessage


class ConversationPanel(Widget):
    """Right column main area: conversation history."""

    DEFAULT_CSS = """
    ConversationPanel {
        width: 100%;
        height: 100%;
        border: solid #30363d;
        background: #0a0e14;
    }

    ConversationPanel > VerticalScroll {
        width: 100%;
        height: 1fr;
        padding: 0 1;
    }

    ConversationPanel #search-input {
        width: 100%;
        height: 1;
        background: #111820;
        border: solid #30363d;
        color: #c9d1d9;
        margin-bottom: 1;
        display: none;
    }

    ConversationPanel #search-input.visible {
        display: block;
    }

    ConversationPanel RichLog {
        width: 100%;
        height: 1fr;
    }

    ConversationPanel .user-msg {
        color: #61dafb;
    }

    ConversationPanel .assistant-msg {
        color: #d4a76a;
    }

    ConversationPanel .tool-msg {
        color: #79c0ff;
    }

    ConversationPanel .system-msg {
        color: #6e7681;
        text-style: dim;
    }

    ConversationPanel .streaming-caret {
        color: #d4a76a;
        text-style: blink;
    }

    ConversationPanel .tool-started {
        color: #79c0ff;
    }

    ConversationPanel .tool-running {
        color: #d29922;
    }

    ConversationPanel .tool-done {
        color: #3fb950;
    }

    ConversationPanel .tool-fail {
        color: #f85149;
    }

    ConversationPanel .search-highlight {
        background: #d4a76a;
        color: #0a0e14;
        text-style: bold;
    }

    ConversationPanel .search-match {
        background: #d29922;
        color: #0a0e14;
    }
    """

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.state = state
        self._last_msg_count = 0
        self._search_query = ""
        self._search_matches: list[int] = []
        self._current_match_index = -1
        self._search_active = False

    def compose(self) -> Widget:
        with VerticalScroll(id="scroll"):
            yield Input(placeholder="Search conversation... (Ctrl+F to focus, Esc to close)", id="search-input")
            yield RichLog(id="log", markup=True, highlight=False, wrap=True)

    def on_mount(self) -> None:
        self._update()

    def watch_state(self) -> None:
        self._update()

    # Search-related bindings
    BINDINGS = [
        ("ctrl+f", "toggle_search", "Toggle Search"),
        ("escape", "close_search", "Close Search"),
        ("f3", "next_match", "Next Match"),
        ("shift+f3", "prev_match", "Previous Match"),
    ]

    def _update(self) -> None:
        log = self.query_one("#log", RichLog)

        if len(self.state.conversation) == self._last_msg_count:
            # Check if last message is streaming (might need caret update)
            if self.state.conversation and self.state.conversation[-1].streaming:
                self._render_streaming_update(log)
            return

        # Full re-render for new messages
        log.clear()
        for msg in self.state.conversation:
            self._render_message(log, msg)

        self._last_msg_count = len(self.state.conversation)
        log.scroll_end(animate=False)

        # Re-apply search highlights if search is active
        if self._search_active and self._search_query:
            self._apply_search_highlights()

    def _update(self) -> None:
        log = self.query_one("#log", RichLog)

        if len(self.state.conversation) == self._last_msg_count:
            # Check if last message is streaming (might need caret update)
            if self.state.conversation and self.state.conversation[-1].streaming:
                self._render_streaming_update(log)
            return

        # Full re-render for new messages
        log.clear()
        for msg in self.state.conversation:
            self._render_message(log, msg)

        self._last_msg_count = len(self.state.conversation)
        log.scroll_end(animate=False)

        # Re-apply search highlights if search is active
        if self._search_active and self._search_query:
            self._apply_search_highlights()

    def action_toggle_search(self) -> None:
        """Toggle search input visibility."""
        if self._search_active:
            self._close_search()
        else:
            self._open_search()

    def _open_search(self) -> None:
        """Open the search input."""
        search_input = self.query_one("#search-input", Input)
        search_input.display = True
        search_input.focus()
        self._search_active = True

    def action_close_search(self) -> None:
        """Close the search input."""
        self._close_search()

    def _close_search(self) -> None:
        """Close the search input and clear results."""
        search_input = self.query_one("#search-input", Input)
        search_input.display = False
        search_input.value = ""
        self._search_query = ""
        self._search_matches = []
        self._current_match_index = -1
        self._search_active = False
        self._clear_search_highlights()
        self.query_one("#log", RichLog).focus()

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "search-input":
            self._search_query = event.value
            self._perform_search()

    def _perform_search(self) -> None:
        """Perform search on conversation messages."""
        query = self._search_query.lower().strip()
        if not query:
            self._search_matches = []
            self._current_match_index = -1
            self._clear_search_highlights()
            return

        self._search_matches = []
        for i, msg in enumerate(self.state.conversation):
            if query in msg.content.lower():
                self._search_matches.append(i)

        if self._search_matches:
            self._current_match_index = 0
            self._scroll_to_match(self._search_matches[0])
        else:
            self._current_match_index = -1

        self._apply_search_highlights()

    def _apply_search_highlights(self) -> None:
        """Apply search highlights to matching messages."""
        if not self._search_query:
            return

        log = self.query_one("#log", RichLog)
        # Re-render all messages with highlights
        log.clear()
        for i, msg in enumerate(self.state.conversation):
            self._render_message_with_highlight(log, msg, i in self._search_matches)

        # Scroll to current match
        if self._search_matches and 0 <= self._current_match_index < len(self._search_matches):
            self._scroll_to_match(self._search_matches[self._current_match_index])

    def _render_message_with_highlight(self, log: RichLog, msg: ConversationMessage, is_match: bool) -> None:
        """Render a single message with optional search highlight."""
        if msg.role == "user":
            content = f"[span.user-msg]You >[/span] {msg.content}"
        elif msg.role == "assistant":
            caret = " [span.streaming-caret]▌[/span]" if msg.streaming else ""
            content = f"[span.assistant-msg]A.S.I.S. >[/span] {msg.content}{caret}"
        elif msg.role == "tool":
            if msg.tool_status == "STARTED":
                prefix = "[span.tool-started][TOOL][/span]"
            elif msg.tool_status == "RUNNING":
                prefix = "[span.tool-running][RUN ][/span]"
            elif msg.tool_status == "DONE":
                prefix = "[span.tool-done][DONE][/span]"
            elif msg.tool_status == "FAIL":
                prefix = "[span.tool-fail][FAIL][/span]"
            else:
                prefix = "[span.tool-msg][TOOL][/span]"
            content = f"{prefix} {msg.content}"
        elif msg.role == "system":
            content = f"[span.system-msg]{msg.content}[/span]"
        else:
            content = msg.content

        if is_match and self._search_query:
            # Wrap the matching text with highlight
            query = self._search_query
            highlighted_content = content
            # Simple highlight - replace the query with highlighted version
            import re
            pattern = re.compile(re.escape(query), re.IGNORECASE)
            highlighted_content = pattern.sub(lambda m: f"[span.search-highlight]{m.group()}[/span]", content)
            content = highlighted_content

        log.write(content)

    def _clear_search_highlights(self) -> None:
        """Clear search highlights by re-rendering without highlights."""
        if not self._search_active:
            return
        log = self.query_one("#log", RichLog)
        log.clear()
        for msg in self.state.conversation:
            self._render_message(log, msg)

    def _scroll_to_match(self, match_index: int) -> None:
        """Scroll to a specific match."""
        log = self.query_one("#log", RichLog)
        # RichLog doesn't have direct line scrolling, but we can try
        log.scroll_end(animate=False)

    def action_next_match(self) -> None:
        """Go to next search match."""
        if not self._search_matches:
            return
        self._current_match_index = (self._current_match_index + 1) % len(self._search_matches)
        self._scroll_to_match(self._search_matches[self._current_match_index])

    def action_prev_match(self) -> None:
        """Go to previous search match."""
        if not self._search_matches:
            return
        self._current_match_index = (self._current_match_index - 1) % len(self._search_matches)
        self._scroll_to_match(self._search_matches[self._current_match_index])

    def _render_message(self, log: RichLog, msg: ConversationMessage) -> None:
        """Render a single message."""
        if msg.role == "user":
            content = f"[span.user-msg]You >[/span] {msg.content}"
        elif msg.role == "assistant":
            caret = " [span.streaming-caret]▌[/span]" if msg.streaming else ""
            content = f"[span.assistant-msg]A.S.I.S. >[/span] {msg.content}{caret}"
        elif msg.role == "tool":
            if msg.tool_status == "STARTED":
                prefix = "[span.tool-started][TOOL][/span]"
            elif msg.tool_status == "RUNNING":
                prefix = "[span.tool-running][RUN ][/span]"
            elif msg.tool_status == "DONE":
                prefix = "[span.tool-done][DONE][/span]"
            elif msg.tool_status == "FAIL":
                prefix = "[span.tool-fail][FAIL][/span]"
            else:
                prefix = "[span.tool-msg][TOOL][/span]"
            content = f"{prefix} {msg.content}"
        elif msg.role == "system":
            content = f"[span.system-msg]{msg.content}[/span]"
        else:
            content = msg.content

        log.write(content)

    async def append_user_message(self, content: str) -> None:
        """Append a user message (called from input handler)."""
        log = self.query_one("#log", RichLog)
        log.write(f"[span.user-msg]You >[/span] {content}")
        log.scroll_end(animate=False)

    async def start_assistant_stream(self) -> None:
        """Start streaming assistant response."""
        log = self.query_one("#log", RichLog)
        log.write("[span.assistant-msg]A.S.I.S. >[/span] ")
        log.scroll_end(animate=False)

    async def append_assistant_chunk(self, chunk: str) -> None:
        """Append a streaming chunk to the last assistant message."""
        log = self.query_one("#log", RichLog)
        # RichLog doesn't support in-place update easily
        # We'll write the chunk directly - the caret is handled by CSS
        log.write(chunk)
        log.scroll_end(animate=False)

    async def end_assistant_stream(self, final_content: str = "") -> None:
        """End streaming and optionally replace with final content."""
        log = self.query_one("#log", RichLog)
        # The streaming is done via direct writes, so just ensure scroll
        log.scroll_end(animate=False)

    async def add_tool_message(self, tool_name: str, status: str, detail: str = "") -> None:
        """Add a tool status message."""
        log = self.query_one("#log", RichLog)

        if status == "STARTED":
            prefix = "[span.tool-started][TOOL][/span]"
            content = f"{prefix} {tool_name}"
        elif status == "RUNNING":
            prefix = "[span.tool-running][RUN ][/span]"
            content = f"{prefix} {detail or tool_name}"
        elif status == "DONE":
            prefix = "[span.tool-done][DONE][/span]"
            content = f"{prefix} {detail or tool_name}"
        elif status == "FAIL":
            prefix = "[span.tool-fail][FAIL][/span]"
            content = f"{prefix} {detail or tool_name}"
        else:
            prefix = "[span.tool-msg][TOOL][/span]"
            content = f"{prefix} {tool_name}: {detail}"

        log.write(content)
        log.scroll_end(animate=False)

    async def add_system_message(self, content: str) -> None:
        """Add a system message (memory, etc.)."""
        log = self.query_one("#log", RichLog)
        log.write(f"[span.system-msg]{content}[/span]")
        log.scroll_end(animate=False)
