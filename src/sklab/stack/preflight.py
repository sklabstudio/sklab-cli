"""v0.3 preflight: resources, disk, PATH, base deps, node, docker, github auth.

All inspection only - no mutation except when an explicit ``apply_*`` helper
is called after user confirmation (never from dry-run / status / doctor).
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from sklab.core.subprocess import run_command
from sklab.stack.redaction import redact_text

APT_DEPS = (
    ("git", ["git", "--version"], "git"),
    ("curl", ["curl", "--version"], "curl"),
    ("jq", ["jq", "--version"], "jq"),
    ("unzip", ["unzip", "-v"], "unzip"),
    ("python3", ["python3", "--version"], "python3"),
    ("pipx", ["pipx", "--version"], "pipx"),
    ("node", ["node", "--version"], "nodejs"),
    ("npm", ["npm", "--version"], "npm"),
    ("docker", ["docker", "--version"], "docker-ce"),
    ("gh", ["gh", "--version"], "gh"),
)

CA_CERTS_MARKER = "/etc/ssl/certs/ca-certificates.crt"
BUILD_ESSENTIAL_MARKER = "/usr/bin/gcc"

# Conservative per-module disk estimate (repos + venv/node_modules + build).
PER_MODULE_ESTIMATE_MB = 400
# Trivial adapters (argv-only command, local link) need almost no disk.
LIGHT_MODULE_ESTIMATE_MB = 10
HEAVY_INSTALL_TYPES = ("git", "python", "node", "docker-compose")
SETUP_BUFFER_MB = 1024


@dataclass
class HostInfo:
    os_name: str = ""
    cpu_count: int = 0
    ram_mib: int = 0
    swap_mib: int = 0
    disk_free_mb: int = 0
    disk_free_path: str = ""
    python_version: str = ""
    node_version: str = ""


@dataclass
class ResourceVerdict:
    level: str  # RECOMMENDED | SUPPORTED_FOR_TESTING | CONSTRAINED
    warnings: list[str] = field(default_factory=list)


def _read_meminfo() -> tuple[int, int]:
    ram_kb, swap_kb = 0, 0
    try:
        text = Path("/proc/meminfo").read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("MemTotal:"):
                ram_kb = int(line.split()[1])
            elif line.startswith("SwapTotal:"):
                swap_kb = int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return ram_kb // 1024, swap_kb // 1024


def host_info(disk_path: str | None = None) -> HostInfo:
    ram_mib, swap_mib = _read_meminfo()
    if ram_mib <= 0:
        # Non-Linux fallback: do not fabricate; report 0 (unknown).
        ram_mib, swap_mib = 0, 0
    anchor = Path(disk_path) if disk_path else Path.home()
    try:
        usage = shutil.disk_usage(str(anchor))
        free_mb = int(usage.free // (1024 * 1024))
    except OSError:
        free_mb = 0
    node_version = ""
    node_result = run_command(["node", "--version"], timeout=10.0)
    if node_result.ok:
        node_version = node_result.stdout.strip().splitlines()[0].strip() if node_result.stdout.strip() else ""
    return HostInfo(
        os_name=platform.platform(),
        cpu_count=os.cpu_count() or 0,
        ram_mib=ram_mib,
        swap_mib=swap_mib,
        disk_free_mb=free_mb,
        disk_free_path=str(anchor),
        python_version=platform.python_version(),
        node_version=node_version,
    )


def resource_verdict(host: HostInfo) -> ResourceVerdict:
    warnings: list[str] = []
    if host.ram_mib and host.ram_mib < 2048:
        warnings.append(f"Low RAM ({host.ram_mib} MiB): installation may be slow; run heavy modules sequentially.")
    if host.ram_mib and host.ram_mib < 1500 and host.swap_mib < 2048:
        warnings.append("Very low RAM with little swap: add swap before heavy builds.")
    if host.disk_free_mb and host.disk_free_mb < 5120:
        warnings.append(f"Low disk ({host.disk_free_mb} MB free): free space before cloning/building.")
    if host.ram_mib >= 14000:
        return ResourceVerdict(level="RECOMMENDED", warnings=warnings)
    if host.ram_mib == 0:
        return ResourceVerdict(
            level="SUPPORTED_FOR_TESTING",
            warnings=warnings + ["RAM unknown (non-Linux): proceeding cautiously."],
        )
    return ResourceVerdict(level="SUPPORTED_FOR_TESTING", warnings=warnings)


def estimate_disk_mb(module_count: int) -> int:
    return module_count * PER_MODULE_ESTIMATE_MB + SETUP_BUFFER_MB


def estimate_plan_mb(heavy_count: int, light_count: int = 0) -> int:
    """Honest estimate: heavy installs (clone/venv/npm/docker) vs trivial ones."""
    return heavy_count * PER_MODULE_ESTIMATE_MB + light_count * LIGHT_MODULE_ESTIMATE_MB + SETUP_BUFFER_MB


def check_disk_ok(required_mb: int, *, path: str | None = None) -> tuple[bool, str]:
    anchor = Path(path) if path else Path.home()
    try:
        free_mb = int(shutil.disk_usage(str(anchor)).free // (1024 * 1024))
    except OSError as exc:
        return False, f"Cannot inspect free disk at {anchor}: {exc}."
    if free_mb < required_mb:
        return False, (
            f"Dangerously low disk: {free_mb} MB free at {anchor}, "
            f"need ~{required_mb} MB. Aborting before partial installation. "
            "Free space and re-run. Nothing was deleted."
        )
    return True, f"{free_mb} MB free at {anchor}; need ~{required_mb} MB."


# --- PATH bootstrap ---------------------------------------------------------


def user_bin_dir() -> Path:
    return Path.home() / ".local" / "bin"


def path_status() -> dict[str, object]:
    bindir = user_bin_dir()
    on_path = str(bindir) in os.environ.get("PATH", "").split(os.pathsep)
    return {"bin": str(bindir), "on_path": on_path, "path": os.environ.get("PATH", "")}


def shell_config_candidates() -> list[Path]:
    home = Path.home()
    candidates: list[Path] = []
    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        candidates.append(home / ".zshrc")
    candidates.append(home / ".bashrc")
    candidates.append(home / ".profile")
    # Deduplicate, keep order.
    seen: set[str] = set()
    out: list[Path] = []
    for path in candidates:
        if str(path) not in seen:
            seen.add(str(path))
            out.append(path)
    return out


PATH_LINE = 'export PATH="$HOME/.local/bin:$PATH"'
PATH_MARKER = "# sklab: local bin on PATH (managed, idempotent)"


def path_fix_plan() -> list[dict[str, str]]:
    status = path_status()
    if status.get("on_path"):
        return []
    plan: list[dict[str, str]] = []
    for config in shell_config_candidates():
        plan.append({"file": str(config), "line": PATH_LINE})
        break  # first applicable shell config only; never spam every file
    return plan


def apply_path_fix() -> dict[str, object]:
    """Idempotent: append the export line once. Caller must have user approval."""
    plan = path_fix_plan()
    if not plan:
        return {"changed": False, "reason": "already on PATH"}
    target = Path(plan[0]["file"])
    try:
        existing = target.read_text(encoding="utf-8") if target.exists() else ""
    except OSError as exc:
        return {"changed": False, "reason": f"cannot read {target}: {exc}"}
    if PATH_LINE in existing:
        return {"changed": False, "reason": f"already present in {target}"}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            handle.write(f"{PATH_MARKER}\n{PATH_LINE}\n")
    except OSError as exc:
        return {"changed": False, "reason": f"cannot write {target}: {exc}"}
    return {"changed": True, "file": str(target)}


# --- base dependencies ------------------------------------------------------


def detect_base_deps() -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for name, argv, apt in APT_DEPS:
        result = run_command(list(argv), timeout=10.0)
        if result.ok:
            if result.stdout.strip():
                first = result.stdout.strip().splitlines()[0]
            elif result.stderr.strip():
                first = result.stderr.strip().splitlines()[0]
            else:
                first = "available"
            results.append({"name": name, "available": "yes", "version": redact_text(first)[:120], "apt": apt})
        elif result.not_found:
            results.append({"name": name, "available": "no", "version": "", "apt": apt})
        else:
            results.append({"name": name, "available": "no", "version": "", "apt": apt})
    # ca-certificates / build-essential are file-based on Debian/Ubuntu.
    results.append({
        "name": "ca-certificates", "available": "yes" if Path(CA_CERTS_MARKER).exists() else "no",
        "version": "", "apt": "ca-certificates",
    })
    results.append({
        "name": "build-essential", "available": "yes" if Path(BUILD_ESSENTIAL_MARKER).exists() else "no",
        "version": "", "apt": "build-essential",
    })
    results.append({
        "name": "python3-venv", "available": "yes" if _have_pyvenv() else "no",
        "version": "", "apt": "python3-venv",
    })
    results.append({
        "name": "python3-pip", "available": "yes" if _have_pip() else "no",
        "version": "", "apt": "python3-pip",
    })
    # docker compose is a subcommand, not a binary.
    compose = run_command(["docker", "compose", "version"], timeout=10.0)
    compose_version = ""
    if compose.ok and compose.stdout.strip():
        compose_version = redact_text(compose.stdout.strip().splitlines()[0])[:120]
    results.append({
        "name": "docker compose", "available": "yes" if compose.ok else "no",
        "version": compose_version,
        "apt": "docker-compose-plugin",
    })
    return results


def _have_pyvenv() -> bool:
    try:
        import venv  # noqa: F401
        return True
    except ImportError:
        return False


def _have_pip() -> bool:
    return shutil.which("pip3") is not None or shutil.which("pip") is not None


def is_ubuntu() -> bool:
    try:
        text = Path("/etc/os-release").read_text(encoding="utf-8").lower()
        return "ubuntu" in text
    except OSError:
        return False


def apt_install_plan(missing: list[str]) -> list[str]:
    """Structured apt argv (no shell). Caller confirms before execution."""
    if not missing:
        return []
    return ["sudo", "apt-get", "update"] + ["__SEPARATOR__"] + ["sudo", "apt-get", "install", "-y", *missing]


# --- node version -----------------------------------------------------------


def parse_node_major(version: str) -> int | None:
    match = re.search(r"v?(\d+)", (version or "").strip())
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def read_package_engines(repo_dir: Path) -> dict[str, str]:
    package = repo_dir / "package.json"
    if not package.exists():
        return {}
    try:
        data = json.loads(package.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    engines = data.get("engines")
    if isinstance(engines, dict):
        return {str(k): str(v) for k, v in engines.items()}
    return {}


def check_node(repo_dir: Path | None = None) -> dict[str, str]:
    installed = ""
    result = run_command(["node", "--version"], timeout=10.0)
    if result.ok and result.stdout.strip():
        installed = result.stdout.strip().splitlines()[0].strip()
    required = ""
    if repo_dir is not None:
        engines = read_package_engines(repo_dir)
        required = engines.get("node", "")
    major = parse_node_major(installed)
    verdict = "UNKNOWN"
    detail = ""
    if major is None:
        verdict, detail = "NOT_INSTALLED", "Node.js is not installed."
    elif required and "18" in required and major >= 18:
        verdict, detail = "READY", f"Node {installed} satisfies engines {required}."
    elif major >= 20:
        verdict, detail = "READY", f"Node {installed} is a supported LTS."
    elif major == 18:
        verdict = "DEGRADED"
        detail = (
            f"Node {installed} is old. Web UI targets Node 20 LTS; "
            f"engines {required or '>=20'} recommended. "
            "Install Node 20 via your distro's NodeSource setup or nvm "
            "(see docs/vps.md); no curl|bash runs automatically."
        )
    else:
        verdict = "FAILED"
        detail = f"Node {installed} is too old; Node 20 LTS is required."
    return {"installed": installed, "required": required, "verdict": verdict, "detail": detail}


# --- docker -----------------------------------------------------------------


def check_docker() -> dict[str, str]:
    version = run_command(["docker", "--version"], timeout=10.0)
    if version.not_found:
        return {"status": "NOT_INSTALLED", "detail": "docker CLI is not installed."}
    compose = run_command(["docker", "compose", "version"], timeout=10.0)
    compose_note = "" if compose.ok else " (compose plugin missing)"
    daemon = run_command(["docker", "info"], timeout=15.0)
    if daemon.ok:
        first = version.stdout.strip().splitlines()[0] if version.stdout.strip() else "docker"
        return {"status": "READY", "detail": redact_text(first) + compose_note}
    combined = (daemon.stderr + daemon.stdout).lower()
    if "permission denied" in combined or "permissiondenied" in combined:
        return {"status": "PERMISSION_DENIED",
                "detail": "Docker daemon reachable but permission denied; add your user to the docker group."}
    return {"status": "DAEMON_UNAVAILABLE",
            "detail": "Docker CLI is installed but the daemon is not reachable; start dockerd."}


# --- github auth ------------------------------------------------------------


def check_github_auth() -> dict[str, str]:
    gh_result = run_command(["gh", "auth", "status"], timeout=10.0)
    if gh_result.not_found:
        # Fall back to git credential capability: presence of a helper or
        # an existing authenticated remote is enough for public clones.
        helper = run_command(["git", "config", "--global", "credential.helper"], timeout=10.0)
        detail = "gh CLI not installed; public clones need no auth."
        if helper.ok and helper.stdout.strip():
            detail += f" Git credential helper: {helper.stdout.strip().splitlines()[0]}."
        return {"status": "PUBLIC_OK", "detail": detail}
    if gh_result.ok:
        return {"status": "AUTHENTICATED", "detail": "gh is authenticated."}
    return {"status": "AUTH_REQUIRED",
            "detail": "gh is installed but not authenticated. Run 'gh auth login' to enable private modules; "
                      "public modules need no auth. Never paste tokens into logs."}


def python_version() -> str:
    return sys.version.split()[0]
