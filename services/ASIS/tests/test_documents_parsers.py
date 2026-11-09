"""Unit: local document parsers (offline, stdlib-only)."""

from __future__ import annotations

import pytest

from asis.documents.parsers import SUPPORTED_SUFFIXES, parse_file


def test_parse_txt_md_json_csv(tmp_path):
    txt = tmp_path / "a.txt"
    txt.write_text("hello\r\n\r\n\r\nworld\x00", encoding="utf-8")
    assert "hello" in parse_file(txt) and "world" in parse_file(txt)
    md = tmp_path / "b.md"
    md.write_text("# t\nbody", encoding="utf-8")
    assert "body" in parse_file(md)
    js = tmp_path / "c.json"
    js.write_text('{"k": "v"}', encoding="utf-8")
    assert "v" in parse_file(js)
    csvf = tmp_path / "d.csv"
    csvf.write_text("a,b\n1,2\n", encoding="utf-8")
    assert "1" in parse_file(csvf)


def test_parse_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_file(tmp_path / "missing.txt")
    exe = tmp_path / "e.exe"
    exe.write_bytes(b"MZ")
    with pytest.raises(ValueError):
        parse_file(exe)
    assert ".txt" in SUPPORTED_SUFFIXES and ".pdf" in SUPPORTED_SUFFIXES
