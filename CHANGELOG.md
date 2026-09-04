# Changelog

All notable changes to SKLab CLI are documented here.

## 0.3.0 — One-command VPS bootstrap & real installer

- Real idempotent installer: `pipx install "git+https://github.com/sklabstudio/sklab-cli.git"` then
  `sklab setup --all` installs the public stack in dependency order (no more v0.2 conservative skip).
- Adapters execute for real: pipx → isolated venv → pip (python), npm ci/install + build (node),
  clone/fetch/ff-only (git), compose up only when the manifest defines it, argv-only command, local link.
  Every adapter supports plan/install/update/verify/uninstall with structured results.
- Install roots: `/opt/sklab/{repos,runtime,logs}` for root, `~/.local/share/sklab/...` otherwise;
  `SKLAB_HOME` isolation preserved for tests; repos and runtime always separated.
- Preflight: CPU/RAM/swap/disk, disk-safety abort before partial installs, base-dep detection
  (git/curl/jq/unzip/build-essential/python3-venv/pip/pipx/node/npm/docker/gh), Node engines check
  (18 = DEGRADED guidance, never `curl|bash`), Docker READY/DAEMON_UNAVAILABLE/NOT_INSTALLED/
  PERMISSION_DENIED, `gh auth status` handling, PATH bootstrap (`--fix-path`, idempotent).
- Private modules (`appsec-lab`, `protocol-intelligence`) via local manifests only; missing auth reports
  `AUTH_REQUIRED` without crashing public installs; no tokens stored/logged.
- Transaction log per run (`logs/setup-*.log`, redacted), resume/repair via re-running setup,
  structured JSON (`host`, `log`, `resume_hint`), post-setup status/doctor summary.
- `sklab doctor --stack` now also reports base deps, PATH, Docker, Node, GitHub auth, resources.
- Service management (`start/stop/restart`, systemd) deliberately deferred: setup + health scope only.
- Manifest schema v1 unchanged (backward compatible); `AUTH_REQUIRED` added to health statuses.
- 4GB = test/minimum (sequential heavy work), 16GB = recommended full workstation.

## 0.2.0 — Stack setup & integration foundation

- Generic versioned module manifest (`schema_version: 1`, strict validation, argv arrays only).
- Built-in public registry (16 modules) + local `~/.sklab/modules.d/*.yaml` overlay for optional/private modules.
- `PUBLIC → PRIVATE` dependency direction enforced (`PRIVATE → PUBLIC` allowed).
- Dependency resolver: stable ordering, cycle/missing/version detection.
- `sklab setup [--all|--public] [--dry-run] [--json] [--yes]` — idempotent, planned, redacted.
- `sklab status [--json]` — `READY/DEGRADED/FAILED/NOT_INSTALLED/UNAVAILABLE/UNKNOWN`, never fakes `READY`.
- `sklab doctor --stack [--json]` — tools, module health, dependency consistency, writable dirs, no paid AI (repo `doctor` unchanged by default).
- `sklab modules [--json]`, `sklab modules add-manifest`, `sklab module install|remove|doctor`.
- `sklab update [--dry-run]` — ordered plan, safe rollback notes, no force-push/reset.
- `sklab clean [--dry-run] [--yes]` — only SKLab-owned caches/temp.
- Atomic installer state, secret redaction, no telemetry, no `shell=True`.
- Docs: `architecture/modules/setup/private-modules/security/vps/troubleshooting/progress`.

## 0.1.0 — Initial development release

- `sklab init` — create projects from starters (local `--source` or GitHub `sklabstudio/starters`), with `--dry-run`, `--force`, template placeholders, and safe defaults.
- `sklab starters` — list available starters, with `--json`.
- `sklab doctor` — read-only environment/repository diagnostics with adaptive checks, with `--json`.
- `sklab shipcheck` — release readiness checks with plan mode (`--dry-run`), `--json`, timeouts, and exit codes 0/1/2/3.
- `sklab prompts` / `sklab prompt <name>` — browse and print Coding Lab prompts (`--output`, `--copy`).
- `sklab workflows` / `sklab workflow <name>` — browse and print Coding Lab workflows.
- `sklab config show|get|set|reset|path` — TOML config with `SKLAB_*` environment overrides.
- `sklab cache status|clear|refresh` — platformdirs-based cache that never deletes outside its directory.
- `sklab info` — version, runtime, and filesystem locations.
