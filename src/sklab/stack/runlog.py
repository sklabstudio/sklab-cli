"""Structured installer logs with redaction. No telemetry; local files only."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sklab.stack import home as stack_home
from sklab.stack.redaction import redact_text


def new_run_log(prefix: str = "setup") -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    directory = stack_home.system_logs_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{prefix}-{stamp}.log"


def append_event(log: Path, event: str, data: dict[str, Any] | None = None) -> None:
    record = {
        "ts": datetime.now(UTC).isoformat(),
        "event": event,
        "data": data or {},
    }
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as handle:
            handle.write(redact_text(json.dumps(record)) + "\n")
    except OSError:
        pass
