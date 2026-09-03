"""Cross-platform clipboard copy without extra dependencies (best-effort)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Any, cast

from sklab.core.errors import CLIPBOARD_ERROR, SklabError

_WIN_CLIP_SNIPPET = "import sys; from sklab.core.clipboard import _win_clip; _win_clip(sys.stdin.read())"


def copy_to_clipboard(text: str) -> str:
    """Copy *text* to the clipboard. Returns the helper used. Raises SklabError."""
    candidates: list[list[str]] = []
    if sys.platform == "darwin":
        candidates = [["pbcopy"]]
    elif sys.platform == "win32":
        if shutil.which("clip"):
            candidates = [["clip"]]
        candidates.append([sys.executable, "-c", _WIN_CLIP_SNIPPET])
        # Prefer native clip; the powershell fallback is appended below.
        candidates.append(["powershell", "-NoProfile", "-Command", "$Input | Set-Clipboard"])
    else:
        for helper in (["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]):
            if shutil.which(helper[0]):
                candidates.append(helper)

    errors: list[str] = []
    for argv in candidates:
        if not shutil.which(argv[0]) and argv[0] not in (sys.executable, "powershell", "clip"):
            continue
        try:
            subprocess.run(argv, input=text, capture_output=True, text=True, timeout=10, shell=False, check=True)
        except FileNotFoundError:
            continue
        except (subprocess.SubprocessError, OSError) as exc:
            errors.append(f"{argv[0]}: {exc}")
            continue
        return argv[0]
    detail = f" ({'; '.join(errors)})" if errors else ""
    raise SklabError(
        CLIPBOARD_ERROR,
        f"Cannot copy to the clipboard: no working helper found{detail}.",
        remediation="Use --output <file> to save the content to a file instead.",
    )


def _win_clip(text: str) -> None:  # pragma: no cover - windows helper
    import ctypes

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    windll = cast(Any, ctypes).windll
    kernel32 = windll.kernel32
    user32 = windll.user32
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    data = text.encode("utf-16-le") + b"\x00\x00"
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        raise OSError("GlobalAlloc failed")
    locked = ctypes.cast(kernel32.GlobalLock(handle), ctypes.POINTER(ctypes.c_char))
    ctypes.memmove(locked, data, len(data))
    kernel32.GlobalUnlock(handle)
    if not user32.OpenClipboard(None):
        kernel32.GlobalFree(handle)
        raise OSError("OpenClipboard failed")
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            raise OSError("SetClipboardData failed")
    finally:
        user32.CloseClipboard()
