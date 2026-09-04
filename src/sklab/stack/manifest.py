"""SKLab stack module manifest (schema v1): strict, versioned, generic.

PUBLIC stays PUBLIC. PRIVATE stays PRIVATE.
The public CLI only understands this generic contract; it never bundles
private source code, credentials, or proprietary implementation.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

SCHEMA_VERSION = 1

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
CAPABILITY_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

KNOWN_CAPABILITIES = (
    "orchestration",
    "web-ui",
    "skills",
    "security",
    "contracts",
    "benchmarking",
    "sandbox",
    "verification",
    "agents",
    "providers",
    "repo-context",
)

KNOWN_INSTALL_TYPES = (
    "python",
    "node",
    "git",
    "docker-compose",
    "command",
    "local",
)

KNOWN_SOURCE_TYPES = (
    "git",
    "pypi",
    "npm",
    "local",
    "docker",
    "command",
)

# Uppercase aliases from the v0.2 spec (PYTHON_PACKAGE, ...) map here.
_INSTALL_ALIASES = {
    "PYTHON_PACKAGE": "python",
    "NODE_PACKAGE": "node",
    "GIT_SOURCE": "git",
    "DOCKER_COMPOSE": "docker-compose",
    "COMMAND": "command",
    "LOCAL_PATH": "local",
    "LOCAL": "local",
    "DOCKER-COMPOSE": "docker-compose",
    "DOCKER": "docker-compose",
}


def normalize_install_type(raw: str) -> str:
    text = (raw or "").strip()
    if text in KNOWN_INSTALL_TYPES:
        return text
    upper = text.upper().replace("-", "_")
    if upper in _INSTALL_ALIASES:
        return _INSTALL_ALIASES[upper]
    lowered = text.lower().replace("_", "-")
    if lowered in KNOWN_INSTALL_TYPES:
        return lowered
    return text


def _ensure_argv(value: object, *, field_name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty argv array of strings")
    for item in value:
        if not isinstance(item, str) or not item:
            raise ValueError(f"{field_name} must be a non-empty argv array of strings")
    return list(value)


class ModuleSource(BaseModel):
    model_config = {"extra": "forbid"}

    type: str = Field(description="Source type: git|pypi|npm|local|docker|command.")
    repository: str | None = None
    url: str | None = None
    url_env: str | None = None
    ref: str | None = None
    package: str | None = None
    path: str | None = None

    @field_validator("type")
    @classmethod
    def _check_type(cls, value: str) -> str:
        text = (value or "").strip().lower()
        if text not in KNOWN_SOURCE_TYPES:
            raise ValueError(f"Unknown source.type: {value!r}. Expected one of {sorted(KNOWN_SOURCE_TYPES)}.")
        return text

    @model_validator(mode="after")
    def _check_pointer(self) -> ModuleSource:
        # At least one pointer is required so the manifest is actionable,
        # but all forms stay generic (no private code is ever inlined).
        if not any([self.repository, self.url, self.url_env, self.package, self.path]):
            raise ValueError("source must set one of: repository, url, url_env, package, path.")
        if self.url_env is not None and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.url_env):
            raise ValueError(f"Invalid source.url_env: {self.url_env!r}. Must be a valid env var name.")
        return self


class ModuleInstall(BaseModel):
    model_config = {"extra": "forbid"}

    type: str = Field(description="Install adapter: python|node|git|docker-compose|command|local.")
    package: str | None = None
    package_path: str | None = None
    source_dir: str | None = None
    compose_file: str | None = None
    command: list[str] | None = None
    path: str | None = None

    @field_validator("type")
    @classmethod
    def _check_type(cls, value: str) -> str:
        normalized = normalize_install_type(value)
        if normalized not in KNOWN_INSTALL_TYPES:
            raise ValueError(f"Unknown install.type: {value!r}. Expected one of {sorted(KNOWN_INSTALL_TYPES)}.")
        return normalized

    @model_validator(mode="after")
    def _check_command_shape(self) -> ModuleInstall:
        if self.command is not None:
            _ensure_argv(self.command, field_name="install.command")
        if self.type == "command" and not self.command:
            raise ValueError("install.command (argv array) is required when install.type is 'command'.")
        return self


class ModuleHealth(BaseModel):
    model_config = {"extra": "forbid"}

    command: list[str] | None = None
    endpoint: str | None = None
    timeout: float | None = None

    @field_validator("command")
    @classmethod
    def _check_command(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _ensure_argv(value, field_name="health.command")

    @field_validator("timeout")
    @classmethod
    def _check_timeout(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if not isinstance(value, (int, float)) or isinstance(value, bool) or float(value) <= 0:
            raise ValueError("health.timeout must be a positive number of seconds.")
        return float(value)


class ModuleDependency(BaseModel):
    model_config = {"extra": "forbid"}

    id: str
    version: str | None = None
    optional: bool = False

    @field_validator("id")
    @classmethod
    def _check_id(cls, value: str) -> str:
        if not isinstance(value, str) or not ID_RE.fullmatch(value):
            raise ValueError(f"Invalid dependency id: {value!r}.")
        return value


def _parse_dependency(raw: object) -> ModuleDependency:
    if isinstance(raw, str):
        text = raw.strip()
        if not ID_RE.fullmatch(text):
            raise ValueError(f"Invalid dependency id: {raw!r}.")
        return ModuleDependency(id=text)
    if isinstance(raw, dict):
        if "id" not in raw:
            raise ValueError("Dependency mapping must contain 'id'.")
        dep_id = raw["id"]
        if not isinstance(dep_id, str) or not ID_RE.fullmatch(dep_id.strip()):
            raise ValueError(f"Invalid dependency id: {dep_id!r}.")
        version = raw.get("version")
        if version is not None and (not isinstance(version, str) or not version.strip()):
            raise ValueError("Dependency version must be a non-empty string when set.")
        optional = bool(raw.get("optional", False))
        extra = set(raw.keys()) - {"id", "version", "optional"}
        if extra:
            raise ValueError(f"Unknown dependency keys: {sorted(extra)}.")
        return ModuleDependency(id=dep_id.strip(), version=version.strip() if version else None, optional=optional)
    raise ValueError(f"Dependencies must be strings or mappings, got {type(raw).__name__}.")


class ModuleManifest(BaseModel):
    """Stable v1 manifest. Strict: unknown fields are rejected."""

    model_config = {"extra": "forbid"}

    schema_version: Literal[1] = 1
    id: str
    name: str
    version: str = "0.1.0"
    visibility: Literal["public", "private"] = "public"
    source: ModuleSource
    install: ModuleInstall
    executable: str | None = None
    cli: str | None = None
    health: ModuleHealth | None = None
    capabilities: list[str] = Field(default_factory=list)
    dependencies: list[ModuleDependency] = Field(default_factory=list)
    optional_dependencies: list[ModuleDependency] = Field(default_factory=list)
    config_paths: list[str] = Field(default_factory=list)
    env_required: list[str] = Field(default_factory=list)
    service: dict[str, Any] = Field(default_factory=dict)
    web_ui: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _check_id(cls, value: str) -> str:
        if not isinstance(value, str) or not ID_RE.fullmatch(value):
            raise ValueError(f"Invalid module id: {value!r}. Use lowercase letters, digits, hyphens.")
        return value

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Module name must be a non-empty string.")
        if len(value.strip()) > 120:
            raise ValueError("Module name is too long (max 120 chars).")
        return value.strip()

    @field_validator("version")
    @classmethod
    def _check_version(cls, value: str) -> str:
        if not isinstance(value, str) or not VERSION_RE.fullmatch(value.strip()):
            raise ValueError(f"Invalid module version: {value!r}.")
        return value.strip()

    @field_validator("capabilities")
    @classmethod
    def _check_capabilities(cls, value: list[str]) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("capabilities must be a list of strings.")
        seen: set[str] = set()
        out: list[str] = []
        for item in value:
            if not isinstance(item, str) or not CAPABILITY_RE.fullmatch(item.strip()):
                raise ValueError(f"Invalid capability: {item!r}.")
            normalized = item.strip()
            if normalized not in seen:
                seen.add(normalized)
                out.append(normalized)
        return out

    @field_validator("dependencies", "optional_dependencies", mode="before")
    @classmethod
    def _parse_deps(cls, value: object) -> list[ModuleDependency]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("dependencies must be a list.")
        return [_parse_dependency(item) for item in value]

    @field_validator("config_paths", "env_required", mode="before")
    @classmethod
    def _parse_str_lists(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("Expected a list of strings.")
        out: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("Expected a list of non-empty strings.")
            out.append(item.strip())
        return out

    def fingerprint(self) -> str:
        canonical = self.model_dump_json(exclude_none=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @property
    def GerritCommand(self) -> list[str] | None:
        if self.health is not None and self.health.command:
            return list(self.health.command)
        return None

    @property
    def primary_executable(self) -> str | None:
        return self.cli or self.executable


def parse_manifest_dict(data: dict[str, Any]) -> ModuleManifest:
    if not isinstance(data, dict):
        raise ValueError("Manifest must be a mapping.")
    if data.get("schema_version", 1) != 1:
        raise ValueError(f"Unsupported schema_version: {data.get('schema_version')!r}. Expected 1.")
    return ModuleManifest.model_validate(data)


def parse_manifest_yaml(text: str) -> ModuleManifest:
    import yaml

    try:
        data = yaml.safe_load(text)
    except Exception as exc:
        raise ValueError(f"Invalid YAML manifest: {exc}.") from exc
    if not isinstance(data, dict):
        raise ValueError("Manifest YAML must contain a mapping at the top level.")
    return parse_manifest_dict(data)


def manifest_fingerprint_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()
