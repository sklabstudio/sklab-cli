"""Secret redaction for logs and diagnostics. No telemetry."""

from __future__ import annotations

import os
import re

REDACTED = "[REDACTED]"

# Generic secret assignments: token=..., --token ..., "key": "...".
_SECRET_ASSIGN_RE = re.compile(
    r"(?i)\b(token|secret|password|passwd|pwd|api[_-]?key|provider[_-]?key|private[_-]?key|client[_-]?secret)\b"
    r"\s*(=|:|is)\s*(\"[^\"]*\"|'[^']*'|\S+)"
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
# https://user:pass@host or https://token@host
_URL_CREDS_RE = re.compile(r"(https?://)([^/\s:@]+)(?::([^/\s@]*))?@")
# Well-known token prefixes.
_TOKEN_PREFIX_RE = re.compile(
    r"\b((sk-[A-Za-z0-9-_]{4,})|(ghp_[A-Za-z0-9]+)|(gho_[A-Za-z0-9]+)|"
    r"(github_pat_[A-Za-z0-9_]+)|(xox[bap]-[A-Za-z0-9-]+))\b"
)
_QUERY_SECRET_RE = re.compile(r"(?i)([?&](token|key|secret|password|signature)=)[^&\s]+")

_SECRET_ENV_SUFFIXES = ("TOKEN", "SECRET", "PASSWORD", "PRIVATE_KEY", "PROVIDER_KEY", "API_KEY")


def _secret_env_values() -> list[str]:
    values: list[str] = []
    for key, value in os.environ.items():
        upper = key.upper()
        if not value:
            continue
        if upper in {"SKLAB_PRIVATE_MODULE_URL"} or upper.endswith(_SECRET_ENV_SUFFIXES):
            if len(value) >= 3:
                values.append(value)
    # Longest first so substrings do not leave fragments.
    values.sort(key=len, reverse=True)
    return values


def redact_text(text: str) -> str:
    """Redact credentials, tokens, private Git URLs, and secret env values."""
    if not isinstance(text, str) or not text:
        return text
    redacted = text
    redacted = _SECRET_ASSIGN_RE.sub(lambda m: f"{m.group(1)}={REDACTED}", redacted)
    redacted = _BEARER_RE.sub(f"Bearer {REDACTED}", redacted)
    redacted = _URL_CREDS_RE.sub(r"\1" + REDACTED + "@", redacted)
    redacted = _TOKEN_PREFIX_RE.sub(REDACTED, redacted)
    redacted = _QUERY_SECRET_RE.sub(lambda m: f"{m.group(1)}{REDACTED}", redacted)
    for secret in _secret_env_values():
        if secret and secret in redacted:
            redacted = redacted.replace(secret, REDACTED)
    return redacted


def redact_argv(argv: list[str]) -> list[str]:
    return [redact_text(arg) for arg in argv]


def redact_mapping(data: dict[str, object]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in data.items():
        if isinstance(value, str) and (
            key.upper().endswith(_SECRET_ENV_SUFFIXES) or "SECRET" in key.upper() or "TOKEN" in key.upper()
        ):
            out[key] = REDACTED
        elif isinstance(value, str):
            out[key] = redact_text(value)
        elif isinstance(value, dict):
            out[key] = redact_mapping(dict(value))
        elif isinstance(value, list):
            out[key] = [redact_text(v) if isinstance(v, str) else v for v in value]
        else:
            out[key] = value
    return out
