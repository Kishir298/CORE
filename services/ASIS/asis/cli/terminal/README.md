# Terminal UI (`asis/cli/terminal`)

Stdlib-only ANSI panels wired into `../interactive/loop.py`. Legacy
`You >`/`A.S.I.S. >`/`Shutting down.` lines are fully removed; the
streaming prefix is now `A.S.I.S.` + newline and goodbye is the footer.

- `layout.py` — header/conversation/composer/footer, bubbles, badges, attachments bar
- `status.py` — status bar + voice strip + `clean_error`
- `modes.py` — TAB `ModeController` + multiline `Composer` (session untouched)
- `attachments.py` — `AttachmentController` over `DocumentStore` + image vision gate
- `activity.py` — voice states, tool lines, streaming frames, boot block

Display-only tests: `tests/test_terminal_*.py` (mock provider, no Ollama/mic).
Live badges subscribe per-turn to the app `event_bus` (`TOOL_EXECUTION_*`).
