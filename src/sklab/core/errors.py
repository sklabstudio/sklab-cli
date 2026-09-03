"""Consistent user-facing errors for SKLab CLI."""

from __future__ import annotations

# Error codes (stable, user-facing, safe for automation).
STARTER_NOT_FOUND = "STARTER_NOT_FOUND"
DESTINATION_EXISTS = "DESTINATION_EXISTS"
INVALID_PROJECT_NAME = "INVALID_PROJECT_NAME"
UNSAFE_PATH = "UNSAFE_PATH"
NETWORK_ERROR = "NETWORK_ERROR"
DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
INVALID_ARCHIVE = "INVALID_ARCHIVE"
UNSAFE_ARCHIVE_PATH = "UNSAFE_ARCHIVE_PATH"
ARCHIVE_TOO_LARGE = "ARCHIVE_TOO_LARGE"
CONFIG_ERROR = "CONFIG_ERROR"
COMMAND_TIMEOUT = "COMMAND_TIMEOUT"
COMMAND_FAILED = "COMMAND_FAILED"
PROJECT_NOT_DETECTED = "PROJECT_NOT_DETECTED"
RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
CACHE_ERROR = "CACHE_ERROR"
CLIPBOARD_ERROR = "CLIPBOARD_ERROR"
INTERNAL_ERROR = "INTERNAL_ERROR"


class SklabError(Exception):
    """User-facing error with a stable machine-readable code."""

    def __init__(
        self,
        code: str,
        message: str,
        remediation: str | None = None,
        exit_code: int = 1,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.remediation = remediation
        self.exit_code = exit_code

    def to_dict(self) -> dict[str, str | None]:
        return {"code": self.code, "message": self.message, "remediation": self.remediation}

    def format(self) -> str:
        base = f"Error [{self.code}]: {self.message}"
        if self.remediation:
            base += f"\n  Fix: {self.remediation}"
        return base
