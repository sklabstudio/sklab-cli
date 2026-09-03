"""Ship-check models: verdicts and reports."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from sklab.diagnostics.models import CheckResult


class Verdict(StrEnum):
    READY = "READY"
    READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
    NOT_READY = "NOT_READY"


class ShipReport(BaseModel):
    verdict: Verdict
    checks: list[CheckResult] = Field(default_factory=list)
    duration_ms: int = 0
    root: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict.value,
            "checks": [c.to_dict() for c in self.checks],
            "duration_ms": self.duration_ms,
            "root": self.root,
        }


EXIT_READY = 0
EXIT_WARNINGS = 1
EXIT_NOT_READY = 2
EXIT_ERROR = 3


def exit_code_for(verdict: Verdict) -> int:
    return {Verdict.READY: EXIT_READY, Verdict.READY_WITH_WARNINGS: EXIT_WARNINGS, Verdict.NOT_READY: EXIT_NOT_READY}[
        verdict
    ]
