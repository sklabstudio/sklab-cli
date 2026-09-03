"""Output degradation: ASCII fallbacks when stdout cannot render ✓/✗."""

from __future__ import annotations

import io
import sys

from sklab.core import output


def test_status_symbols_unicode_by_default() -> None:
    assert output.status_symbol("PASS") in ("✓", "+")
    assert output.status_symbol("FAIL") in ("✗", "x")


def test_ascii_fallback_on_cp1252(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    wrapper = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", wrapper)
    try:
        assert output._ascii_only() is True
        assert output.status_symbol("PASS") == "+"
        assert output.status_symbol("FAIL") == "x"
        assert output.status_symbol("WARNING") == "!"
        output.success("ok-message")
        output.warning("warn-message")
    finally:
        wrapper.detach()
    assert output.status_symbol("PASS") in ("✓", "+")


def test_json_always_ascii_safe(capsys) -> None:  # type: ignore[no-untyped-def]
    output.print_json({"verdict": "READY", "checks": []})
    captured = capsys.readouterr()
    captured.out.encode("cp1252")


def test_print_text_never_crashes_on_cp1252(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    wrapper = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", wrapper)
    try:
        output.print_text("# Title → with arrow and ✓ check")
        wrapper.flush()
    finally:
        raw = wrapper.buffer.getvalue()
        wrapper.detach()
    assert raw, "expected fallback output to be written"
    raw.decode("cp1252")  # must be decodable in the console encoding
