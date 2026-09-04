# Setup

```sh
sklab setup --public --dry-run
sklab setup --public --yes
sklab setup --all --dry-run
sklab setup --all --yes
sklab status
sklab status --json
```

## Flow (`setup --public`)

1. Inspect platform + required base tools (`python/node/git/docker`).
2. Inspect existing installations (health checks, markers, executables).
3. Resolve module dependency order (stable topological sort).
4. Show the plan (or `--json` machine output).
5. Install/upgrade public modules via conservative adapters.
6. Create config dirs (`~/.sklab/{config,modules.d,state,logs,cache}`).
7. Run health checks.
8. Summarize `READY / DEGRADED / FAILED / SKIPPED`.

Idempotent: running setup twice never destroys a working install; `READY`
modules are skipped.

## `--all`

- Installs all configured public modules **plus** optional locally-registered
  modules when available and authenticated.
- Inaccessible optional modules skip cleanly (`SKIPPED`/`UNAVAILABLE`).
- Never leaks their source details (redacted logs, no telemetry — there is none).

## Dry run (mandatory)

```sh
sklab setup --all --dry-run
```

Shows the exact dependency-ordered plan with zero installs/modifications.

## Install methods

`python | node | git | docker-compose | command | local`, all argv-only,
timeouts, no `shell=True`. v0.2 is conservative: remote package installs that
are not locally actionable are reported as `SKIPPED` (never faked `READY`).

## Dependency graph

Detects cycles, missing required modules, unavailable modules, incompatible
versions (exact or `>=`). Stable alphabetical ordering.

## Config/install roots

- Config root `~/.sklab/` (`SKLAB_HOME` overrides for tests).
- Install roots: `USER / VENV / SOURCE / DOCKER` conceptually; default writes
  markers under `~/.sklab/modules/<id>/` and never `sudo`-escalates silently.
  If root is required, the CLI reports it instead of escalating.

## Update

```sh
sklab update --dry-run
sklab update --yes
```

Compares versions/manifest fingerprints, updates in dependency order, runs
health, rolls back only where the adapter safely supports it (`local`,
`command`), and reports incomplete rollback honestly. No force-push, no
destructive git reset.

## Clean

```sh
sklab clean --dry-run
sklab clean --yes
```

Removes only SKLab-owned caches/temp (`*.tmp/*.log/*.cache` under
`~/.sklab/{cache,logs,modules}`, plus `~/.sklab/tmp`). Never deletes user
repos or persistent run history.
