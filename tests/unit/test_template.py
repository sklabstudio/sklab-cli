"""Template substitution: placeholders only, binaries untouched, no code execution."""

from __future__ import annotations

from sklab.starters.template import process_templates, render_text


def test_render_placeholders() -> None:
    assert render_text("# {{PROJECT_NAME}} ({{PROJECT_SLUG}})", "Invoice App") == "# Invoice App (invoice-app)"


def test_render_leaves_unknown_placeholders(tmp_path) -> None:
    assert render_text("{{NOT_A_THING}} {{PROJECT_NAME}}", "demo") == "{{NOT_A_THING}} demo"


def test_process_templates_substitutes(tmp_path) -> None:
    (tmp_path / "README.md").write_text("# {{PROJECT_NAME}} {{PROJECT_SLUG}}", encoding="utf-8")
    changed = process_templates(tmp_path, "My App")
    assert changed == 1
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "# My App my-app"


def test_process_templates_skips_binary(tmp_path) -> None:
    binary = tmp_path / "logo.png"
    binary.write_bytes(b"\x89PNG\r\n\x1a\n\x00\xff\xfe{{PROJECT_NAME}}")
    changed = process_templates(tmp_path, "demo")
    assert changed == 0
    assert binary.read_bytes().startswith(b"\x89PNG")


def test_process_templates_never_executes(tmp_path) -> None:
    marker = tmp_path / "pwned.txt"
    payload = "{{PROJECT_NAME}} {% import os %}{{ os.system('touch ' + '" + str(marker) + "') }}"
    (tmp_path / "evil.md").write_text(payload, encoding="utf-8")
    process_templates(tmp_path, "demo")
    assert not marker.exists()
    assert "{% import os %}" in (tmp_path / "evil.md").read_text(encoding="utf-8")
