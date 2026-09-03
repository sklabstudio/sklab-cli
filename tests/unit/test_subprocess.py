"""Windows .cmd/.bat shim handling in run_command (regression tests).

Real-world case: `npm` on Windows resolves to `npm.cmd`, which CreateProcess
cannot launch directly. Without the shim, shipcheck falsely reported npm as
missing on machines where it is installed.
"""

from __future__ import annotations

from sklab.core.subprocess import _apply_windows_shim


def _fake_which(mapping: dict[str, str | None]):  # type: ignore[no-untyped-def]
    def _which(name: str) -> str | None:
        return mapping.get(name)

    return _which


def test_cmd_shim_routed_through_comspec(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import sklab.core.subprocess as sp

    monkeypatch.setattr(sp.shutil, "which", _fake_which({"npm": "C:\\Program Files\\nodejs\\npm.CMD"}))
    monkeypatch.setenv("COMSPEC", "C:\\Windows\\system32\\cmd.exe")
    resolved = _apply_windows_shim(["npm", "run", "lint"], os_name="nt")
    assert resolved == (
        'C:\\Windows\\system32\\cmd.exe /d /s /c ""C:\\Program Files\\nodejs\\npm.CMD" run lint"'
    )


def test_exe_left_alone_on_windows(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import sklab.core.subprocess as sp

    monkeypatch.setattr(sp.shutil, "which", _fake_which({"node": "C:\\Program Files\\nodejs\\node.EXE"}))
    assert _apply_windows_shim(["node", "--version"], os_name="nt") == ["node", "--version"]


def test_missing_binary_left_alone(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import sklab.core.subprocess as sp

    monkeypatch.setattr(sp.shutil, "which", _fake_which({}))
    assert _apply_windows_shim(["npm", "--version"], os_name="nt") == ["npm", "--version"]


def test_no_rewrite_off_windows(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import sklab.core.subprocess as sp

    monkeypatch.setattr(sp.shutil, "which", _fake_which({"npm": "/usr/local/bin/npm"}))
    assert _apply_windows_shim(["npm", "--version"], os_name="posix") == ["npm", "--version"]
