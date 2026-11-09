"""A.S.I.S. TUI Main Application.

Full alternate-screen TUI with two-column layout, responsive breakpoints,
and real-time backend integration.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from typing import Any

from rich.console import Console
from textual import constants, events
from textual.app import App, ComposeResult, Control, ScreenStackError
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import Reactive
from textual.timer import Timer
from textual.widgets import Static, RichLog

# Import backend modules
from asis.app.assistant import AssistantApp
from asis.app.modes import AssistantMode as AppAssistantMode
from asis.configuration import settings
from asis.events import EventBus
from asis.app.boot import BootError
from asis.logging.logger import configure_logging
from asis.tui.boot_orchestrator import run_boot_sequence_legacy
from asis.tui.config import load_tui_settings, save_tui_setting
from asis.tui.events import EventBridge, create_event_bridge
from asis.tui.state import AppState
from asis.tui.widgets import (
    AttachmentsBar,
    BootLogPanel,
    ConversationPanel,
    HeaderBar,
    IdentityPanel,
    InputBox,
    ModeFooterPanel,
    StatusBar,
    StatusPanel,
    VoiceBar,
)
from asis.voice.pipeline import VoicePipeline


class ASISTUI(App):
    """A.S.I.S. Terminal User Interface."""

    TITLE = "A.S.I.S."
    SUB_TITLE = "A Smart Intelligence System"

    # Responsive breakpoints - Textual auto-applies these classes to Screen based on width
    # Classes accumulate: at width 100, both -narrow and -normal apply; at 130, all three apply
    HORIZONTAL_BREAKPOINTS = [
        (0, "-narrow"),      # < 90 columns: single column, sidebar hidden (base styles)
        (90, "-normal"),     # 90-119 columns: two column layout
        (120, "-wide"),      # ≥120 columns: two column with full sidebar
    ]

    # Vertical breakpoints for height-based responsive layout
    VERTICAL_BREAKPOINTS = [
        (0, "-short"),       # < 30 rows: compact layout
        (30, "-normal"),     # 30-44 rows: standard layout
        (45, "-tall"),       # ≥45 rows: expanded layout with more conversation space
    ]

    # Theme mode (dark/light) - reactive so CSS refreshes on change
    theme_mode = Reactive("dark")

    # Color theme matching spec exactly
    CSS = """
    Screen {
        background: $background;
        color: $text;
    }

    #main-grid {
        layout: grid;
        grid-size: 1;
        grid-columns: 1fr;
        grid-rows: 11% 18% 32% 35% 7% 20% 7% 1;
        grid-gutter: 0;
        height: 100%;
    }

    #left-column {
        display: none;
        transition: width 200ms ease-in-out, opacity 150ms ease-in-out;
    }

    /* Collapsed sidebar in grid mode (normal/wide screens) */
    #left-column.collapsed {
        display: none;
        animation: slide-out 150ms ease-in forwards;
    }

    /* Expanded sidebar on narrow screens (overlay via Ctrl+B) */
    #left-column.expanded {
        display: block;
        position: absolute;
        top: 0;
        left: 0;
        width: 28;
        height: 100%;
        background: $surface;
        border-right: solid $panel-border;
        z-index: 100;
        animation: slide-in 200ms ease-out;
    }

    @keyframes slide-in {
        from {
            opacity: 0;
            transform: translateX(-100%);
        }
        to {
            opacity: 1;
            transform: translateX(0);
        }
    }

    @keyframes slide-out {
        from {
            opacity: 1;
            transform: translateX(0);
        }
        to {
            opacity: 0;
            transform: translateX(-100%);
        }
    }

    #right-column {
        column-span: 1;
        row-span: 8;
        display: block;
    }

    #right-grid {
        layout: grid;
        grid-size: 1;
        grid-rows: 11% 50% 7% 20% 7%;
        height: 100%;
    }

    StatusBar {
        row-span: 1;
        column-span: 1;
    }

    #too-narrow {
        display: none;
        width: 100%;
        height: 100%;
        content-align: center middle;
        color: $error;
    }

    /* ===== VERTICAL BREAKPOINTS ===== */

    /* Short terminal (< 30 rows): compact layout */
    Screen.-short #main-grid {
        grid-rows: 8% 12% 30% 40% 5% 15% 5% 1;
    }

    Screen.-short #right-grid {
        grid-rows: 8% 55% 7% 20% 10%;
    }

    Screen.-short HeaderBar {
        height: auto;
        min-height: 1;
    }

    Screen.-short StatusBar {
        height: auto;
        min-height: 1;
    }

    Screen.-short ModeFooterPanel {
        height: auto;
        min-height: 1;
    }

    /* Tall terminal (≥ 45 rows): expanded conversation space */
    Screen.-tall #main-grid {
        grid-rows: 10% 15% 30% 38% 7% 20% 5% 1;
    }

    Screen.-tall #right-grid {
        grid-rows: 10% 60% 5% 18% 7%;
    }

    Screen.-tall ConversationPanel {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Exit", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
        Binding("tab", "toggle_mode", "Toggle Mode", show=False),
        Binding("ctrl+b", "toggle_sidebar", "Toggle Sidebar", show=False),
        Binding("ctrl+t", "toggle_theme", "Toggle Theme", show=True),
    ]

    def __init__(
        self,
        mock_mode: bool = False,
        ai_provider: str | None = None,
        ai_model: str | None = None,
        ai_temperature: float | None = None,
        ai_think: str | None = None,
        ai_num_predict: int | None = None,
        ai_keep_alive: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)

        # Load TUI settings from config file
        tui_config = load_tui_settings()

        self.state = AppState()
        # Apply saved TUI settings to state
        self.state.left_column_collapsed = tui_config.get("sidebar_collapsed", False)
        self.theme_mode = tui_config.get("theme", "dark")

        # Store inference options from CLI
        self.state.ai_temperature = ai_temperature
        self.state.ai_think = ai_think
        self.state.ai_num_predict = ai_num_predict
        self.state.ai_keep_alive = ai_keep_alive
        self.mock_mode = mock_mode
        self.ai_provider = ai_provider
        self.ai_model = ai_model

        self.event_bus = EventBus()
        self.event_bridge: EventBridge | None = None
        self.assistant_app: AssistantApp | None = None
        self.voice_pipeline: VoicePipeline | None = None
        self.boot_task: asyncio.Task | None = None
        self._ollama_owned = False
        self._core_manager = None
        self._core_ctx = None

    def get_css_variables(self) -> dict[str, str]:
        """Return CSS variables for theming.
        
        These variables can be used in CSS with $variable syntax.
        Returns different values based on theme_mode (dark/light).
        """
        if self.theme_mode == "light":
            return {
                "background": "#fdf6e3",       # solarized light base
                "surface": "#eee8d5",          # solarized light surface
                "panel-border": "#93a1a1",     # solarized light border
                "text": "#586e75",             # solarized light text
                "text-dim": "#93a1a1",         # solarized light dim text
                "identity-teal": "#2aa198",    # teal accent
                "prompt-cyan": "#268bd2",      # cyan prompt
                "prompt-amber": "#b58900",     # amber prompt
                "tool-tag": "#268bd2",         # tool tags
                "success": "#859900",          # green success
                "warning": "#cb4b16",          # amber warning
                "error": "#dc322f",            # red error
                "accent": "#2aa198",           # teal accent
            }
        # Default dark theme
        return {
            "background": "#0a0e14",
            "surface": "#111820",
            "panel-border": "#30363d",
            "text": "#c9d1d9",
            "text-dim": "#6e7681",
            "identity-teal": "#5ee6d0",
            "prompt-cyan": "#61dafb",
            "prompt-amber": "#d4a76a",
            "tool-tag": "#79c0ff",
            "success": "#3fb950",
            "warning": "#d29922",
            "error": "#f85149",
            "accent": "#5ee6d0",
        }

    def compose(self) -> ComposeResult:
        """Create the UI layout."""
        yield Static("Terminal too narrow (minimum 60 columns)", id="too-narrow")

        with Horizontal(id="main-grid"):
            # Left column
            with Vertical(id="left-column"):
                yield IdentityPanel(self.state)
                yield StatusPanel(self.state)
                yield BootLogPanel(self.state)
                yield ModeFooterPanel(self.state)

            # Right column
            with Vertical(id="right-column"), Vertical(id="right-grid"):
                yield HeaderBar(self.state)
                yield ConversationPanel(self.state)
                yield AttachmentsBar(self.state)
                yield InputBox(self.state)
                yield VoiceBar(self.state)

            # Status bar (full width)
            yield StatusBar(self.state)

    async def on_mount(self) -> None:
        """Initialize the application."""
        # Configure logging
        configure_logging()

        # Set up event bridge
        self.event_bridge = create_event_bridge(self.state, self.event_bus)

        # Disable input until boot completes
        input_box = self.query_one(InputBox)
        input_box.placeholder = "Booting..."
        input_box.disabled = True

        # Start boot sequence
        self.boot_task = asyncio.create_task(self._run_boot_sequence())

        # Set up input handler (will be enabled after boot)
        input_box.focus()

    async def _process_messages(
        self,
        ready_callback=None,
        headless=False,
        inline=False,
        inline_no_clear=False,
        mouse=True,
        terminal_size=None,
        message_hook=None,
    ) -> None:
        """Fixed version that properly captures nested functions as closures."""
        self._thread_init()

        async def app_prelude() -> bool:
            """Work required before running the app."""
            await self._init_devtools()
            self.log.system("---")
            self.log.system(loop=asyncio.get_running_loop())
            self.log.system(features=self.features)
            if constants.LOG_FILE is not None:
                _log_path = os.path.abspath(constants.LOG_FILE)
                self.log.system(f"Writing logs to {_log_path!r}")

            try:
                if self.css_path:
                    self.stylesheet.read_all(self.css_path)
                for read_from, css, tie_breaker, scope in self._get_default_css():
                    self.stylesheet.add_source(
                        css,
                        read_from=read_from,
                        is_default_css=True,
                        tie_breaker=tie_breaker,
                        scope=scope,
                    )
                if self.CSS:
                    try:
                        app_path = inspect.getfile(self.__class__)
                    except (TypeError, OSError):
                        app_path = ""
                    read_from = (app_path, f"{self.__class__.__name__}.CSS")
                    self.stylesheet.add_source(
                        self.CSS, read_from=read_from, is_default_css=False
                    )
            except Exception as error:
                self._handle_exception(error)
                self._print_error_renderables()
                return False

            if self.css_monitor:
                self.set_interval(0.25, self.css_monitor, name="css monitor")
                self.log.system("STARTED", self.css_monitor)
            return True

        async def run_process_messages():
            """The main message loop."""

            async def invoke_ready_callback() -> None:
                if ready_callback is not None:
                    ready_result = ready_callback()
                    if inspect.isawaitable(ready_result):
                        await ready_result

            with self.batch_update():
                try:
                    try:
                        await self._dispatch_message(events.Compose())
                        await self._dispatch_message(
                            events.Resize.from_dimensions(self.size, None)
                        )
                        default_screen = self.screen
                        self.stylesheet.apply(self)
                        await self._dispatch_message(events.Mount())
                        self.check_idle()
                    finally:
                        self._mounted_event.set()
                        self._is_mounted = True

                    Reactive._initialize_object(self)

                    if self.screen is not default_screen:
                        self.stylesheet.apply(default_screen)

                    await self.animator.start()

                except Exception:
                    await self.animator.stop()
                    raise

                finally:
                    self._running = True
                    await self._ready()
                    await invoke_ready_callback()

            try:
                await self._process_messages_loop()
            except asyncio.CancelledError:
                pass
            finally:
                self.workers.cancel_all()
                self._running = False
                try:
                    await self.animator.stop()
                finally:
                    await Timer._stop_all(self._timers)

        with self._context():
            if not await app_prelude():
                return
            try:
                load_event = events.Load()
                await self._dispatch_message(load_event)

                driver = self._driver = self._build_driver(
                    headless=headless,
                    inline=inline,
                    mouse=mouse,
                    size=terminal_size,
                )
                self.log(driver=driver)

                if not self._exit:
                    driver.start_application_mode()
                    try:
                        with redirect_stdout(self._capture_stdout):
                            with redirect_stderr(self._capture_stderr):
                                await run_process_messages()

                    finally:
                        Reactive._clear_watchers(self)
                        if self._driver.is_inline:
                            cursor_x, cursor_y = self._previous_cursor_position
                            self._driver.write(
                                Control.move(-cursor_x, -cursor_y).segment.text
                            )
                            self._driver.flush()
                            if inline_no_clear and not self.app._exit_renderables:
                                console = Console()
                                try:
                                    console.print(self.screen._compositor)
                                except ScreenStackError:
                                    console.print()
                            else:
                                self._driver.write(
                                    Control.move(0, -self.INLINE_PADDING).segment.text
                                )

                        driver.stop_application_mode()
            except Exception as error:
                self._handle_exception(error)

    async def _run_boot_sequence(self) -> None:
        """Run the boot sequence asynchronously using the BootOrchestrator."""
        # Get boot log panel if available (not available in headless mode)
        boot_log_panel = None
        try:
            boot_log_panel = self.query_one(BootLogPanel)
        except Exception:
            pass  # Headless mode or not mounted yet

        try:
            components = await run_boot_sequence_legacy(
                state=self.state,
                event_bus=self.event_bus,
                boot_log_panel=boot_log_panel,
                mock_mode=getattr(self, "mock_mode", False),
                ai_provider=getattr(self, "ai_provider", None),
                ai_model=getattr(self, "ai_model", None),
            )

            # Assign components to instance attributes
            self.assistant_app = components.get("assistant_app")
            self.voice_pipeline = components.get("voice_pipeline")

            # The boot sequence already sets these on state, but we also need
            # to keep local references for backward compatibility
            self._ollama_owned = components.get("ollama_owned", False)

            # Boot successful - enable input (only if not headless)
            try:
                input_box = self.query_one(InputBox)
                input_box.placeholder = "Type a message..."
                input_box.disabled = False
            except Exception:
                pass  # Headless mode

        except BootError as exc:
            # Boot failed - log error, disable input, stay mounted
            self.state.add_boot_log("FAIL", f"Boot failed: {exc}")
            try:
                input_box = self.query_one(InputBox)
                input_box.placeholder = "Boot failed - see log above"
                input_box.disabled = True
            except Exception:
                pass
        except Exception as exc:
            self.state.add_boot_log("FAIL", f"Boot failed: {exc}")
            try:
                input_box = self.query_one(InputBox)
                input_box.placeholder = "Boot failed - see log above"
                input_box.disabled = True
            except Exception:
                pass

        # Trigger UI refresh (already on app thread)
        try:
            self.refresh()
        except Exception:
            pass

    async def on_input_box_message_sent(self, message: InputBox.MessageSent) -> None:
        """Handle user message sent."""
        if not self.assistant_app:
            return

        # Don't process messages until model is ready
        if not self.state.model_ready:
            conv_panel = self.query_one(ConversationPanel)
            await conv_panel.add_system_message("Model not ready yet. Please wait for boot to complete.")
            return

        text = message.text

        # Handle slash commands
        if text.startswith("/"):
            await self._handle_slash_command(text)
            return

        # Add user message to conversation
        conv_panel = self.query_one(ConversationPanel)
        await conv_panel.append_user_message(text)

        # Process through assistant
        asyncio.create_task(self._process_assistant_response(text))

    async def _process_assistant_response(self, text: str) -> None:
        """Process assistant response with streaming."""
        if not self.assistant_app:
            return

        conv_panel = self.query_one(ConversationPanel)
        await conv_panel.start_assistant_stream()

        full_response = ""

        def on_chunk(chunk: str) -> None:
            nonlocal full_response
            full_response += chunk
            # Schedule UI update
            self.call_from_thread(conv_panel.append_assistant_chunk, chunk)

        try:
            # Run in thread to avoid blocking UI
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.assistant_app.chat_streamed(text, on_chunk=on_chunk)
            )
        except Exception as exc:
            await conv_panel.add_system_message(f"Error: {exc}")
        finally:
            await conv_panel.end_assistant_stream()

    async def _handle_slash_command(self, text: str) -> None:
        """Handle slash commands."""
        conv_panel = self.query_one(ConversationPanel)
        parts = text[1:].split(" ", 1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "help":
            help_text = (
                "Available commands:\n"
                "  /help           Show this help\n"
                "  /status         Show system status\n"
                "  /model          Show current model\n"
                "  /memory         Show memory status\n"
                "  /tools          List available tools\n"
                "  /system         Show system info\n"
                "  /mode [general|coding|translation]  Set mode\n"
                "  /voice          Toggle voice mode\n"
                "  /permissions    Show permission status\n"
                "  /clear          Clear conversation\n"
                "  /exit           Exit A.S.I.S.\n"
                "  /upload <path>  Attach document\n"
                "  /docs           List attachments\n"
                "  /detach <name>  Remove attachment"
            )
            await conv_panel.add_system_message(help_text)

        elif cmd == "status":
            await conv_panel.add_system_message(
                f"MODEL: {self.state.model_name}\n"
                f"OLLAMA: {'ONLINE' if self.state.ollama_online else 'OFFLINE'}\n"
                f"MEMORY: {'READY' if self.state.memory_ready else 'OFFLINE'}\n"
                f"TOOLS: {'READY' if self.state.tools_ready else 'OFFLINE'}\n"
                f"VOICE: {self.state.voice_state.value}\n"
                f"MODE: {self.state.assistant_mode.value}\n"
                f"INTERACTION: {self.state.interaction_mode.value}"
            )

        elif cmd == "model":
            await conv_panel.add_system_message(f"Current model: {self.state.model_name}")

        elif cmd == "memory":
            await conv_panel.add_system_message(
                f"Memory: {'READY' if self.state.memory_ready else 'OFFLINE'}"
            )

        elif cmd == "tools":
            if self.assistant_app:
                tools = self.assistant_app.tools_router.registry.list_names()
                await conv_panel.add_system_message("Available tools:\n" + "\n".join(f"  {t}" for t in tools))
            else:
                await conv_panel.add_system_message("Tools not initialized")

        elif cmd == "system":
            await conv_panel.add_system_message(
                f"A.S.I.S. v0.1.0\n"
                f"Terminal: {self.state.terminal_width}x{self.state.terminal_height}\n"
                f"Python: {sys.version.split()[0]}"
            )

        elif cmd == "mode":
            if not arg:
                await conv_panel.add_system_message(f"Current mode: {self.state.assistant_mode.value}")
            elif arg.lower() in ("general", "coding", "translation"):
                mode_map = {
                    "general": AppAssistantMode.GENERAL,
                    "coding": AppAssistantMode.CODING,
                    "translation": AppAssistantMode.TRANSLATION,
                }
                self.state.set_assistant_mode(mode_map[arg.lower()])
                if self.assistant_app:
                    self.assistant_app.set_mode(mode_map[arg.lower()])
                await conv_panel.add_system_message(f"Mode set to: {arg.upper()}")
            else:
                await conv_panel.add_system_message("Usage: /mode [general|coding|translation]")

        elif cmd == "voice":
            new_mode = self.state.toggle_interaction_mode()
            await conv_panel.add_system_message(f"Interaction mode: {new_mode.value}")

        elif cmd == "permissions":
            await conv_panel.add_system_message("Permission system: ACTIVE")

        elif cmd == "clear":
            self.state.conversation.clear()
            conv_panel.query_one("#log", RichLog).clear()
            await conv_panel.add_system_message("Conversation cleared")

        elif cmd == "exit":
            self.exit()

        elif cmd in ("upload", "attach"):
            if arg:
                from pathlib import Path
                file_path = Path(arg).expanduser().resolve()
                if not file_path.exists():
                    await conv_panel.add_system_message(f"File not found: {arg}")
                elif not file_path.is_file():
                    await conv_panel.add_system_message(f"Not a file: {arg}")
                else:
                    # Determine file type/icon
                    suffix = file_path.suffix.lower()
                    icon_map = {
                        ".py": "🐍", ".js": "📜", ".ts": "📜", ".json": "📋",
                        ".md": "📝", ".txt": "📄", ".pdf": "📕", ".csv": "📊",
                        ".png": "🖼️", ".jpg": "🖼️", ".jpeg": "🖼️", ".gif": "🖼️",
                        ".mp3": "🎵", ".wav": "🎵", ".mp4": "🎬", ".mov": "🎬",
                    }
                    icon = icon_map.get(suffix, "📎")
                    name = file_path.name
                    self.state.add_attachment(name, str(file_path))
                    await conv_panel.add_system_message(f"Attached: {icon} {name} ({file_path})")
            else:
                await conv_panel.add_system_message("Usage: /upload <path>")

        elif cmd == "docs":
            if self.state.attachments:
                await conv_panel.add_system_message("Attachments:")
                for att in self.state.attachments:
                    await conv_panel.add_system_message(f"  {att.icon} {att.name} ({att.path})")
            else:
                await conv_panel.add_system_message("No attachments")

        elif cmd == "detach":
            if arg and self.state.remove_attachment(arg):
                await conv_panel.add_system_message(f"Detached: {arg}")
            else:
                await conv_panel.add_system_message("Usage: /detach <name>")

        else:
            await conv_panel.add_system_message(f"Unknown command: {cmd} (try /help)")

    async def on_input_box_input_cancelled(self, message: InputBox.InputCancelled) -> None:
        """Handle ESC - cancel current operation."""
        if self.state.generating and self.assistant_app:
            # Cancel in-flight generation
            interrupts = getattr(self.assistant_app, "interrupts", None)
            if interrupts:
                interrupts.cancel_all()
            self.state.generating = False
            conv_panel = self.query_one(ConversationPanel)
            await conv_panel.add_system_message("[Interrupted]")

    async def on_input_box_attach_clicked(self, message: InputBox.AttachClicked) -> None:
        """Handle attach button - open file browser modal."""
        from pathlib import Path
        from asis.tui.widgets.file_browser_modal import FileBrowserModal

        def on_file_selected(path: Path | None) -> None:
            if path is None:
                return

            file_path = Path(path).expanduser().resolve()
            if not file_path.exists():
                asyncio.create_task(conv_panel.add_system_message(f"File not found: {path}"))
                return
            if not file_path.is_file():
                asyncio.create_task(conv_panel.add_system_message(f"Not a file: {path}"))
                return

            # Determine file type/icon
            suffix = file_path.suffix.lower()
            icon_map = {
                ".py": "🐍", ".js": "📜", ".ts": "📜", ".json": "📋",
                ".md": "📝", ".txt": "📄", ".pdf": "📕", ".csv": "📊",
                ".png": "🖼️", ".jpg": "🖼️", ".jpeg": "🖼️", ".gif": "🖼️",
                ".mp3": "🎵", ".wav": "🎵", ".mp4": "🎬", ".mov": "🎬",
            }
            icon = icon_map.get(suffix, "📎")
            name = file_path.name
            self.state.add_attachment(name, str(file_path))
            asyncio.create_task(conv_panel.add_system_message(f"Attached: {icon} {name} ({file_path})"))

        conv_panel = self.query_one(ConversationPanel)
        self.push_screen(FileBrowserModal(), callback=on_file_selected)

    async def on_mode_footer_panel_mode_changed(self, message: ModeFooterPanel.ModeChanged) -> None:
        """Handle mode toggle from footer panel."""
        self.state.interaction_mode = message.mode
        if self.assistant_app:
            # Voice mode toggle is handled by the interaction loop
            pass
        self.refresh()

    async def on_resize(self, event: Any) -> None:
        """Handle terminal resize - update state for other components."""
        self.state.update_terminal_size(event.size.width, event.size.height)
        self.refresh()

    def action_toggle_mode(self) -> None:
        """Toggle interaction mode (Tab key)."""
        new_mode = self.state.toggle_interaction_mode()
        conv_panel = self.query_one(ConversationPanel)
        asyncio.create_task(conv_panel.add_system_message(f"Interaction mode: {new_mode.value}"))

    def action_toggle_sidebar(self) -> None:
        """Toggle left sidebar (Ctrl+B)."""
        left_col = self.query_one("#left-column", Vertical)

        if self.state.terminal_width < 90:
            # Narrow screen: toggle expanded overlay
            if left_col.has_class("expanded"):
                left_col.remove_class("expanded")
                left_col.add_class("collapsed")
                self.state.left_column_collapsed = True
            else:
                left_col.remove_class("collapsed")
                left_col.add_class("expanded")
                self.state.left_column_collapsed = False
        else:
            # Normal/wide screen: toggle collapsed in grid
            if left_col.has_class("collapsed"):
                left_col.remove_class("collapsed")
                self.state.left_column_collapsed = False
            else:
                left_col.add_class("collapsed")
                self.state.left_column_collapsed = True

        # Persist sidebar state
        save_tui_setting("sidebar_collapsed", self.state.left_column_collapsed)

    def action_toggle_theme(self) -> None:
        """Toggle theme between dark and light (Ctrl+T)."""
        self.theme_mode = "light" if self.theme_mode == "dark" else "dark"
        self.refresh_css()
        try:
            conv_panel = self.query_one(ConversationPanel)
            asyncio.create_task(conv_panel.add_system_message(f"Theme: {self.theme_mode}"))
        except Exception:
            # Ignore if ConversationPanel not available (e.g., in tests)
            pass

        # Persist theme preference
        save_tui_setting("theme", self.theme_mode)

    def action_cancel(self) -> None:
        """Handle ESC key."""
        self.post_message(InputBox.InputCancelled())

    async def action_quit(self) -> None:
        """Graceful shutdown (Ctrl+C)."""
        await self._shutdown()
        self.exit()

    async def _shutdown(self) -> None:
        """Shutdown all subsystems in correct order."""
        self.state.shutdown_requested = True

        # 1. Cancel boot task FIRST to prevent races
        if self.boot_task and not self.boot_task.done():
            self.boot_task.cancel()
            try:
                await self.boot_task
            except asyncio.CancelledError:
                # Expected when we cancel our own task
                pass
            except Exception:
                # Suppress other exceptions during boot cancellation
                pass

        # 2. Stop voice pipeline
        if self.voice_pipeline:
            with contextlib.suppress(Exception):
                self.voice_pipeline.stop()

        # 3. Stop core manager
        if self._core_manager and self._core_ctx:
            with contextlib.suppress(Exception):
                self._core_manager.stop(self._core_ctx)

        # 4. Stop owned Ollama
        if self._ollama_owned:
            with contextlib.suppress(Exception):
                from asis.ai.ollama_lifecycle import stop_owned_ollama
                stop_owned_ollama(self._ollama_owned, shutdown_timeout=settings.ollama.shutdown_timeout)

        # 5. Unsubscribe events LAST
        if self.event_bridge:
            with contextlib.suppress(Exception):
                self.event_bridge.unsubscribe_all()

    def on_unmount(self) -> None:
        """Cleanup on unmount."""
        # Schedule shutdown on the event loop - it will run when the loop continues
        try:
            asyncio.create_task(self._shutdown())
        except Exception:
            pass


def entry(argv: list[str] | None = None) -> int:
    """Console entry point for asis-tui."""
    import argparse
    import sys

    # Use sys.argv[1:] when argv is None (direct module launch)
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(description="A.S.I.S. TUI", add_help=False)
    parser.add_argument("--mock", action="store_true", help="Run in mock mode (no Ollama required)")
    parser.add_argument("--provider", choices=["mock", "ollama"], help="AI provider to use")
    parser.add_argument("--model", help="Model to use")
    parser.add_argument("--ai-temperature", type=float, help="Set AI temperature")
    parser.add_argument("--ai-think", choices=["auto", "true", "false"], help="Set AI think mode")
    parser.add_argument("--ai-num-predict", type=int, help="Set max tokens to predict")
    parser.add_argument("--ai-keep-alive", type=str, help="Set model keep-alive duration")
    # Parse known args, leave the rest for potential future use
    args, _ = parser.parse_known_args(argv)

    app = ASISTUI(
        mock_mode=args.mock,
        ai_provider=args.provider,
        ai_model=args.model,
        ai_temperature=args.ai_temperature,
        ai_think=args.ai_think,
        ai_num_predict=args.ai_num_predict,
        ai_keep_alive=args.ai_keep_alive,
    )
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(entry())
