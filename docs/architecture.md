# SKLab CLI v0.2 — Architecture

Public setup/control layer for the SKLab workstation. The CLI is PUBLIC and
stays PUBLIC; private modules attach locally through a generic manifest
contract without ever bundling private code.

## Layers

```text
sklab/cli.py
  commands/setup_cmd.py, status_cmd.py, modules_cmd.py, update_cmd.py, clean_cmd.py
  commands/doctor.py (+ --stack), starters/init/shipcheck/prompts/workflows (v0.1, unchanged)
stack/
  manifest.py    strict v1 schema (pydantic, extra=forbid, argv arrays only)
  registry.py    builtin public descriptors + ~/.sklab/modules.d/*.yaml overlay
  resolver.py    stable topological sort, cycle/missing/version/visibility checks
  adapters.py    conservative installers: python/node/git/docker-compose/command/local
  operations.py  setup/status/doctor/update/clean business logic (testable, no Typer)
  state.py       atomic JSON state (~/.sklab/state/install-state.json)
  redaction.py   token/credential/URL/secret-env redaction, no telemetry
  home.py        ~/.sklab layout (SKLAB_HOME/SKLAB_MODULES_DIR/SKLAB_INSTALL_ROOT overrides)
core/
  subprocess.py  argv-only execution, timeouts, Windows .cmd shim (no shell=True)
  output.py      Rich tables + valid-JSON-only stdout
```

## Key invariants

- `PUBLIC → PRIVATE` dependencies are impossible (validated in the resolver).
- `PRIVATE → PUBLIC` and `PUBLIC → PUBLIC` are allowed.
- Health is inspected, never invented: `READY / DEGRADED / FAILED /`
  `NOT_INSTALLED / UNAVAILABLE / UNKNOWN`.
- `setup --dry-run` shows the exact plan with zero side effects.
- Setup/update/clean are idempotent and conservative; no network side effects
  for remote installs in v0.2 unless the source is locally actionable.
- State is advisory; `doctor --stack` always re-inspects the real system.
- No `shell=True`, no `curl|bash`, no arbitrary hooks, no hidden sudo,
  no secret logging, no telemetry, no paid AI in diagnostics.
