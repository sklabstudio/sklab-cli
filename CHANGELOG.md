# Changelog

All notable changes to SKLab CLI are documented here.

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
