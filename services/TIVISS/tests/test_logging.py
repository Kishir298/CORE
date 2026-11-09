import io
import json
import logging

from tiviss.log import (
    REDACTED,
    JsonFormatter,
    get_logger,
    log_event,
    read_records,
    redact,
)


def test_redact_drops_secrets():
    cleaned = redact(
        {
            "user": "k",
            "session_token": "abc",
            "nested": {"api_key": "K", "tags": ["a", {"password": "p"}]},
        }
    )
    assert cleaned["user"] == "k"
    assert cleaned["session_token"] == REDACTED
    assert cleaned["nested"]["api_key"] == REDACTED
    assert cleaned["nested"]["tags"][1] == {"password": REDACTED}


def test_json_lines_shape():
    stream = io.StringIO()
    logger = get_logger("tiviss.test.shape", stream=stream)
    log_event(
        logger,
        event="message.received",
        agent_id="a-1",
        component="cli",
        request_id="r-1",
        outcome="ok",
        details={"session_token": "abc", "n": 1},
    )
    records = read_records(stream)
    assert len(records) == 1
    record = records[0]
    assert record["level"] == "INFO"
    assert record["details"]["event"] == "message.received"
    assert record["details"]["session_token"] == REDACTED
    assert record["details"]["n"] == 1
    assert "timestamp" in record


def test_logger_no_duplicate_handlers():
    first = get_logger("tiviss.test.dedupe")
    second = get_logger("tiviss.test.dedupe")
    assert first is second
    assert sum(1 for h in first.handlers if getattr(h, "_tiviss_json", False)) == 1


def test_error_field_and_level():
    stream = io.StringIO()
    logger = get_logger("tiviss.test.err", stream=stream)
    log_event(logger, event="tool.failed", error="boom", level=logging.ERROR)
    record = read_records(stream)[0]
    assert record["level"] == "ERROR"
    assert record["details"]["error"] == "boom"


def test_formatter_is_json():
    formatter = JsonFormatter()
    assert isinstance(formatter, logging.Formatter)
    assert "password" not in json.dumps({"a": 1})
