# SKLab CLI

**Developer workflows, project starters, diagnostics and release checks from SKLab Studio.**

```sh
sklab init fullstack my-app
sklab doctor
sklab shipcheck
```

## Why

Software projects repeatedly need:

- reliable starters,
- environment diagnostics,
- pre-release verification,
- reusable coding workflows.

SKLab CLI provides a consistent interface.

## Installation

Requires Python 3.12+.

```sh
pip install .
# or
pipx install .
```

Verify:

```sh
sklab --version
```

No secrets, no accounts, no telemetry. The CLI only touches the network to
download public SKLab resources (starters, Coding Lab content).

## Quick Start

```sh
sklab starters
sklab init api my-api
cd my-api
sklab doctor
sklab shipcheck
```

## Commands

| Command | Purpose |
|---|---|
| `sklab init <starter> <name>` | Create a project from a starter |
| `sklab starters` | List available starters |
| `sklab doctor` | Diagnose the environment/repository (read-only) |
| `sklab shipcheck` | Release readiness checks (may run tests/builds) |
| `sklab prompts` / `sklab prompt <name>` | List / print a Coding Lab prompt |
| `sklab workflows` / `sklab workflow <name>` | List / print a Coding Lab workflow |
| `sklab config show\|get\|set\|reset\|path` | Manage configuration |
| `sklab cache status\|clear\|refresh` | Manage the local resource cache |
| `sklab info` | Show version, runtime, and paths |

Global options: `--verbose`, `--quiet`, `--no-color`. Commands that support
machine output accept `--json`. Global options go before the subcommand:

```sh
sklab --no-color doctor
sklab --verbose shipcheck
```

## Project Starters

```sh
sklab starters
sklab init fullstack invoice-app
sklab init api my-api --dry-run
sklab init frontend my-site --source ./path/to/starters
```

Available starters:

- `fullstack` — Next.js + FastAPI + PostgreSQL
- `api` — FastAPI + PostgreSQL
- `frontend` — Next.js + TypeScript

Safety rules:

- project names must be plain directory names (no paths, no traversal),
- existing destinations are never overwritten unless `--force` is given,
- `--dry-run` shows what would happen without writing files,
- templates only substitute `{{PROJECT_NAME}}` / `{{PROJECT_SLUG}}` — no code
  execution, no automatic script runs,
- remote archives are size-capped and extracted with path-traversal protection.

## Doctor

```sh
cd some-project
sklab doctor
sklab doctor --json
sklab doctor --path ./other-project
```

Checks adapt to the repository: Python checks only run for Python projects,
Node checks only for Node projects, Docker checks only where Docker files
exist. `doctor` is inspection-only — it never installs, modifies, or starts
anything. Statuses: `PASS`, `WARNING`, `FAIL`, `SKIPPED`, `UNKNOWN`.

## Ship Check

```sh
sklab shipcheck
sklab shipcheck --dry-run
sklab shipcheck --json
sklab shipcheck --timeout 300
```

Shipcheck plans checks from real project config (existing `pytest` setup,
existing `npm test|lint|build` scripts, compose files) and runs them with
timeouts. Verdicts and exit codes:

| Verdict | Meaning | Exit code |
|---|---|---|
| `READY` | all checks passed | 0 |
| `READY_WITH_WARNINGS` | warnings, no failures | 1 |
| `NOT_READY` | at least one failure | 2 |
| internal/CLI error | — | 3 |

## Coding Lab Integration

```sh
sklab prompts
sklab prompt audit-repository
sklab prompt audit-repository --output audit.md
sklab prompt audit-repository --copy
sklab workflows
sklab workflow repo-rescue
```

Content is cached locally (see `sklab cache`). Use `--source` to point at a
local checkout and `--refresh` to re-fetch remote content.

## Configuration

```sh
sklab config show
sklab config get starters_source
sklab config set network_timeout 30
sklab config reset
sklab config path
```

Settings: `starters_source`, `coding_lab_source`, `default_branch`,
`network_timeout`, `cache_ttl`. Environment variables override the file:

- `SKLAB_STARTERS_SOURCE`
- `SKLAB_CODING_LAB_SOURCE`
- `SKLAB_DEFAULT_BRANCH`
- `SKLAB_NETWORK_TIMEOUT`
- `SKLAB_CACHE_TTL`

`SKLAB_CONFIG_FILE` and `SKLAB_CACHE_DIR` override the config/cache locations
(used by the test-suite to stay hermetic).

## JSON output

`starters`, `doctor`, `shipcheck`, `prompts`, `workflows`, `config show`,
`cache status`, and `info` accept `--json` and print a single valid JSON
document to stdout.

## Exit codes

- `0` success (shipcheck: `READY`)
- `1` generic error (shipcheck: `READY_WITH_WARNINGS`)
- `2` shipcheck `NOT_READY`
- `3` internal/CLI error

Errors use stable codes (`STARTER_NOT_FOUND`, `DESTINATION_EXISTS`,
`NETWORK_ERROR`, …). Full tracebacks only appear with `--verbose`.

## Development

```sh
pip install . pytest ruff mypy build httpx
python -m pytest
ruff check .
mypy src/sklab
python -m build
```

## Testing

Tests are offline by default: local starter fixtures under
`tests/fixtures/starters`, Coding Lab fixtures under
`tests/fixtures/coding-lab`, and mocked HTTP for archive tests.

```sh
python -m pytest
```

## Security

- archive path-traversal protection with unpack limits,
- subprocess calls use argument arrays (never `shell=True`) with timeouts,
- destination validation; no silent overwrites or deletes,
- starter content is treated as files, never executed,
- environment secrets are never logged (only non-secret settings are shown).

## Roadmap (not built yet)

`sklab new`, plugin system, additional starters, remote starter registries,
Coding Lab agent-role retrieval, interactive setup, project upgrade assistant,
GitHub release integration, optional AI-provider integrations.

## License

MIT — Copyright (c) 2026 SKLab Studio. See [LICENSE](LICENSE).
Website: https://sklab.cc
