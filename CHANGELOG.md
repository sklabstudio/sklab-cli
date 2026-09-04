# Changelog

All notable changes to SKLab CLI are documented here.

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
