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
