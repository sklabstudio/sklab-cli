# SKLab CLI v0.3 — Architecture

Public setup/control layer for the SKLab workstation (real one-command VPS
bootstrap). The CLI is PUBLIC and stays PUBLIC; private modules attach locally
through a generic manifest contract without ever bundling private code.

## Layers

```text
sklab/cli.py
  commands/setup_cmd.py, status_cmd.py, modules_cmd.py, update_cmd.py, clean_cmd.py
  commands/doctor.py (+ --stack), starters/init/shipcheck/prompts/workflows (v0.1, unchanged)
stack/
  manifest.py    strict v1 schema, unchanged (pydantic, extra=forbid, argv arrays only)
  registry.py    builtin public descriptors + ~/.sklab/modules.d/*.yaml overlay
  resolver.py    stable topological sort, cycle/missing/version/visibility checks
  adapters.py    REAL installers: pipx/venv/pip, npm ci+build, git clone/ff-only,
                 compose up (manifest-defined only), argv-only command, local link;
                 plan/install/update/verify/uninstall + structured results
  operations.py  setup/status/doctor/update/clean business logic (testable, no Typer);
                 AUTH_REQUIRED, disk gate, transaction log, resume/repair
  preflight.py   resources, disk, PATH bootstrap, base deps, node engines, docker,
                 gh auth (inspection only; apply_* only after approval)
  state.py       atomic JSON state (~/.sklab/state/install-state.json; reads legacy state.json)
  runlog.py      redacted per-run logs (logs/setup-*.log), local only
  redaction.py   token/credential/URL/secret-env redaction, no telemetry
  home.py        ~/.sklab layout + system roots (/opt/sklab vs XDG; repos/runtime/logs split)
core/
  subprocess.py  argv-only execution, timeouts, Windows .cmd shim (no shell=True)
  output.py      Rich tables + valid-JSON-only stdout
```

## Key invariants

- `PUBLIC → PRIVATE` dependencies are impossible (validated in the resolver).
- `PRIVATE → PUBLIC` and `PUBLIC → PUBLIC` are allowed.
- Health is inspected, never invented: `READY / DEGRADED / FAILED /`
  `NOT_INSTALLED / UNAVAILABLE / AUTH_REQUIRED / UNKNOWN`.
- `setup --dry-run` shows the exact plan with zero side effects (tested).
- Setup/update are idempotent AND resumable; state is advisory;
  `doctor --stack` always re-inspects the real system.
- `status`/`doctor`/list never mutate or hit the network for installs.
- No `shell=True`, no `curl|bash`, no arbitrary hooks, no hidden sudo/apt,
  no secret logging, no telemetry, no paid AI in diagnostics.
