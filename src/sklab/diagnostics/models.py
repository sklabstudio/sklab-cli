"""Shared diagnostic models (doctor + shipcheck)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CheckStatus(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"
    UNKNOWN = "UNKNOWN"


class CheckResult(BaseModel):
    id: str = Field(description="Stable machine-readable check id, e.g. 'python'.")
    name: str = Field(description="Human-readable check name.")
    status: CheckStatus
    message: str
    details: dict[str, object] = Field(default_factory=dict)
    remediation: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "check": self.id,
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "remediation": self.remediation,
        }
