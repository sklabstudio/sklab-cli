# SKLab CLI — progress

## Phase 1 — Repository setup and CLI foundation
- [x] `pyproject.toml` (hatchling, `sklab` entry point, ruff/mypy/pytest config)
- [x] `src/sklab` package with `cli.py` + `commands/` wiring
- [x] Global `--version` / `--verbose` / `--quiet` / `--no-color`

## Phase 2 — Configuration/output/error architecture
- [x] `core/errors.py` — stable error codes (`STARTER_NOT_FOUND`, …)
- [x] `core/output.py` — Rich output with NO_COLOR / quiet / JSON discipline
- [x] `core/config.py` — TOML config + `SKLAB_*` env overrides
- [x] `core/paths.py` — platformdirs locations
- [x] `core/subprocess.py` — argv-only execution with timeouts
- [x] `core/clipboard.py` — dependency-free cross-platform copy

## Phase 3 — Starter provider + init
- [x] `StarterProvider` / `GitHubStarterProvider` / `LocalStarterProvider`
- [x] `sklab init` with validation, `--dry-run`, `--force`, `--source`, `--branch`
- [x] Template substitution (`{{PROJECT_NAME}}`, `{{PROJECT_SLUG}}`), no code exec
- [x] Archive traversal protection + download/unpack limits

## Phase 4 — Doctor
- [x] `diagnostics/detector.py` — file-based technology detection
- [x] `diagnostics/checks.py` — adaptive, read-only checks
- [x] `sklab doctor [--path] [--json]`

## Phase 5 — Shipcheck
- [x] `release/planner.py` — plan from real config only (never invents scripts)
- [x] `release/runner.py` — timeouts, captured output, verdicts
- [x] `sklab shipcheck [--dry-run] [--json] [--timeout]`; exits 0/1/2/3

## Phase 6 — Coding Lab resource integration
- [x] `resources/coding_lab.py` — shared fetcher, local + cached GitHub
- [x] `sklab prompts` / `sklab prompt <name> [--output] [--copy]`
- [x] `sklab workflows` / `sklab workflow <name> [--output] [--copy]`

## Phase 7 — Cache/config commands
- [x] `sklab config show|get|set|reset|path`
- [x] `sklab cache status|clear|refresh` (never deletes outside cache dir)
- [x] `sklab info`

## Phase 8 — Tests
- [x] Unit: validation, templates, archives, detector/doctor, shipcheck, config, cache, resources
- [x] Integration: real CLI invocations via CliRunner
- [x] Offline-only suite (fixtures + mocked HTTP)

## Phase 9 — Packaging/CI
- [x] `python -m build` wheel
- [x] `.github/workflows/ci.yml` (win/mac/linux × py3.12/3.13)
- [x] ruff + mypy configured

## Phase 10 — Documentation and final audit
- [x] README / CHANGELOG / LICENSE
- [ ] Final audit results recorded below
- [ ] Live remote integration test against `sklabstudio/starters` (pending: verify at publish time)
- [ ] Publish `sklabstudio/sklab-cli` to `main`

## Verification log

- `python -m pytest`: **108 passed** (offline; fixtures + mocked HTTP).
- `ruff check .`: **all checks passed**.
- `mypy src/sklab`: **no issues in 30 source files**.
- `python -m build`: wheel + sdist built successfully.
- Clean-venv install of the wheel: `sklab --version` → `sklab 0.1.0`.
- Manual CLI verification (installed wheel, Windows 11, cp1252 console):
  - `sklab starters`, `init fullstack invoice-app --dry-run` and real `init` (3 files, templates rendered, git init, exit 0),
  - `doctor` on the generated project (adaptive SKIPPED/PASS/WARNING, exit 0),
  - `shipcheck` on dirty tree → `NOT_READY`, exit 2; `--dry-run` plan printed,
  - `prompts` / `prompt` / `workflows` / `workflow` / `config show` / `cache status` / `info`.
- Live read-only integration against `sklabstudio/coding-lab@main`: 12 prompts listed, `audit-repository` + `production-hardening` fetched, 60 files cached.
- `sklabstudio/starters` does not exist yet → live starter integration **pending** (by design; CLI verified with local fixtures, no starter files invented).
- Two real bugs found by verification and fixed: Unicode crash on cp1252 consoles (ASCII fallbacks + safe text printing, covered by `tests/unit/test_output.py`); Windows platformdirs ignoring env overrides (added `SKLAB_CONFIG_FILE`/`SKLAB_CACHE_DIR`, test-suite hermetic).

## Real integration verification (2026-09-04, against live repos)
- `sklabstudio/starters@main`: `init` × fullstack/api/frontend — correct dirs, nesting, hidden files, no cross-leakage, no leftover placeholders; dry-run writes nothing; existing destinations rejected; 404s → clean `DOWNLOAD_FAILED`, exit 1.
- `sklabstudio/coding-lab@main`: 12 prompts + 8 workflows listed; 4 resources byte-identical to remote blobs; cache fetch → cached read → refresh → clear → refetch all verified.
- Real bug found and fixed: on Windows, `npm` (an `npm.cmd` shim) was misreported as missing because CreateProcess cannot launch batch files. `run_command` now routes `.cmd`/`.bat` through `cmd /s /c` with exact-byte quoting (no `shell=True`), covered by `tests/unit/test_subprocess.py`. Verified: `npm --version` → 12.0.2; shipcheck executes (rather than skips) npm lint/build, reporting truthful project-state failures.
- Suite at freeze: 112 passed, ruff clean, mypy clean (30 files), wheel rebuilt + clean-venv smoke-tested.

## Phase 11 — v0.2 stack setup & integration foundation (2026-09-04)
- [x] `stack/manifest.py` — strict v1 schema (argv arrays, aliases, fingerprint)
- [x] `stack/registry.py` — 16-module builtin public registry + `modules.d` overlay
- [x] `stack/resolver.py` — stable ordering, cycles, missing, versions, `PUBLIC→PRIVATE` rejection
- [x] `stack/adapters.py` — conservative python/node/git/docker-compose/command/local (no shell)
- [x] `stack/operations.py` — setup/dry-run/status/`doctor --stack`/update/clean
- [x] `stack/state.py` — atomic JSON state; `stack/redaction.py` — no telemetry
- [x] Commands: `setup`, `status`, `modules(+add-manifest)`, `module install|remove|doctor`, `update`, `clean`
- [x] `doctor` preserves v0.1 repo behavior; `--stack` adds workstation health (no paid AI)
- [x] Fixtures: public-python/node, optional, private-local, missing-dep, cycle-a/b, failed/degraded health
- [x] Tests: 37 unit + 15 CLI integration (offline, hermetic `SKLAB_HOME`); full suite 164 passed
- [x] Docs: architecture/modules/setup/private-modules/security/vps/troubleshooting/progress; README/CHANGELOG; version 0.2.0
- [x] Gate: `pytest` 164 passed, `ruff` clean, `mypy` clean (44 files), `python -m build` + wheel smoke
- [ ] Pending concurrently-built integrations: real public repos expose varied CLIs/install flows; builtin
      health probes are generic (`<cli> --version`) and report `NOT_INSTALLED` until repos land — never faked
      `READY`. Recorded here; no probing, no waiting, no private code copied.
- [ ] Publish `sklabstudio/sklab-cli` `main` (commit + push + Actions green) when credentials available.

## Phase 12 — v0.3 one-command VPS bootstrap & real installer
- [x] `stack/home.py` — `/opt/sklab` (root) vs XDG data dir + `repos/`/`runtime/`/`logs` split (v0.2 paths kept)
- [x] `stack/preflight.py` — resources/disk/PATH/base-deps/node-engines/docker-states/gh-auth (inspect-only)
- [x] `stack/adapters.py` — REAL plan/install/update/verify/uninstall: pipx→venv→pip, npm ci+build,
      git clone/fetch ff-only, compose-up only when defined, argv-only command, symlink-aware local
- [x] `stack/operations.py` — `AUTH_REQUIRED`, disk-safety abort, redacted run logs, resume/repair hints
- [x] `stack/runlog.py`, `stack/state.py` legacy `state.json` read path
- [x] Setup UX (Host + Plan + AUTH rows, `--fix-path`, `--yes`), `doctor --stack` new sections,
      `status` auth line; services (`start/stop/restart`) deliberately deferred to next phase
- [x] Tests `tests/unit/test_v03.py` (24): dry-run purity, 2nd-run idempotency, failed-step resume,
      disk gate, private-absent/present, injection/traversal/symlink/redaction/shell-AST, PATH idempotency,
      node/docker/gh-auth/resource/roots/web-ui-smoke/git-offline/doctor-sections/setup-JSON
- [x] Docs: setup/vps/troubleshooting/architecture/security/private-modules/README/CHANGELOG; version 0.3.0
- [x] Live VPS acceptance (sklab-test, Ubuntu 24.04, 2 vCPU/3.8GB RAM/4.5GB swap/66GB free):
  - `pipx install git+https://github.com/sklabstudio/sklab-cli.git` -> 0.3.0; dry-run pure (no state created)
  - First `setup --all`: 16 real installs; found + fixed 3 live bugs: PATH-less SSH env hid health
    binaries (verified via `--fix-path`, 1 idempotent .bashrc line), content repos got no marker
    (now install_type git), web-ui READY without build (now frontend npm ci + next build + backend venv)
  - Resume run -> 16/16 READY; `module install web-ui` -> real Next.js build OK on Node 18 (+LTS guidance)
  - Module CLIs verified; backend `sklab-web-api` installed + importable; nothing started
    (no containers/services/ports); second `setup --all`: all SKIPPED, no duplicates
- [ ] Gate + publish + CI green (below)
