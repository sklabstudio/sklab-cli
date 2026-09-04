# Setup (v0.3: real one-command VPS bootstrap)

```sh
pipx install "git+https://github.com/sklabstudio/sklab-cli.git"
sklab setup --all --dry-run
sklab setup --all
sklab status
sklab doctor --stack
```

## Modes

```sh
sklab setup --all
sklab setup --public
sklab setup --all --dry-run
sklab setup --public --dry-run
sklab setup --all --yes
```

- `--dry-run`: absolutely no install/network mutation (pure inspection).
- Normal setup: shows the exact Host + Plan summary and asks
  `Proceed with N installs? [y/N]`.
- `--yes`: explicit non-interactive approval for automation/CI/VPS bootstrap
  (also enables the idempotent `--fix-path` behavior).
- No separate `--allow-network`: an explicit confirmed non-dry-run setup is the
  approval. `status`/`doctor`/list commands never perform network installs.

## Flow

1. Preflight: platform, CPU/RAM/swap/disk, base tools, Node engines, Docker,
   GitHub auth, PATH.
2. Inspect existing installations (health checks, markers, executables).
3. Resolve module dependency order (stable topological sort).
4. Disk-safety gate: abort with a clear error before partial installation when
   dangerously low (never deletes unrelated files).
5. Show the plan (or `--json` machine output with `host`, `order`, `plan`).
6. Install in dependency order via real adapters (sequential heavy work).
7. Create config dirs + install roots; optional idempotent PATH bootstrap.
8. Run health checks (`status` + `doctor --stack` equivalents).
9. Summarize `READY / DEGRADED / FAILED / SKIPPED / AUTH_REQUIRED` plus the
   redacted run log path and resume instructions.

Idempotent + resumable: re-running skips `READY`, preserves successes, marks
failures precisely, repairs deterministically. No risky global rollback — only
artifacts owned by the failed step are cleaned.

## `--all`

- Installs all configured public modules **plus** optional locally-registered
  modules when available and authenticated.
- Private modules with missing auth report `AUTH_REQUIRED` (`gh auth login`
  guidance) without crashing the public install.
- Never leaks their source details (redacted logs, no telemetry — there is none).

## Dry run contract

```sh
sklab setup --all --dry-run
```

Must NOT clone/fetch/pip-install/npm-install/docker-pull/apt-install, edit
shell config, create services, change firewall, authenticate, or start
containers. It may inspect local system state. Enforced by test.

## Install methods (real)

`python | node | git | docker-compose | command | local`, all argv-only,
timeouts, no `shell=True`.

- python: `pipx install <repo>` → isolated venv + pip → pip package.
- node: `npm ci` (or install) + `npm run build` in the checkout; honors
  `package.json` engines (Node 18 = DEGRADED guidance, never `curl|bash`).
- git: clone/fetch, fast-forward-only updates (never destroys local changes).
- docker-compose: pull/build/start only when the manifest defines a compose
  file (never invents one); Docker socket is not exposed to the Web UI.
- command: manifest-defined argv arrays only. local: existing path, symlink-
  aware, traversal-safe.

## Dependency graph

Detects cycles, missing required modules, unavailable modules, incompatible
versions (exact or `>=`). Stable alphabetical ordering.

## Config/install roots

- Config root `~/.sklab/` (`SKLAB_HOME` overrides for tests).
- System roots: `/opt/sklab/{repos,runtime,logs}` for root,
  `~/.local/share/sklab/{repos,runtime,logs}` otherwise
  (`SKLAB_SYSTEM_ROOT`/`SKLAB_REPOS_DIR`/`SKLAB_RUNTIME_DIR` overrides).
- Checkouts live under `repos/`, generated state under `runtime/` — never
  scattered across `$HOME`. Markers stay under the install root (backward
  compatible). Never `sudo`-escalates silently.

## Prerequisites

Detected (not blindly installed): git, curl, ca-certificates, jq, unzip,
build-essential, python3, python3-venv, python3-pip, pipx, node, npm, docker,
docker compose, gh (optional but useful). On Ubuntu, setup proposes the
reviewed `apt-get install` line after confirmation; it never apt-installs
unprompted.

## Update

```sh
sklab update --dry-run
sklab update --yes
```

Compares versions/manifest fingerprints, updates in dependency order (git
ff-only, reinstall for python/node), runs health, rolls back only where the
adapter safely supports it, and reports incomplete rollback honestly. No
force-push, no destructive git reset.

## Clean

```sh
sklab clean --dry-run
sklab clean --yes
```

Removes only SKLab-owned caches/temp (`*.tmp/*.log/*.cache` under
`~/.sklab/{cache,logs,modules}`, plus `~/.sklab/tmp`). Never deletes user
repos or persistent run history.

## Services

Deliberate v0.3 scope decision: setup + health only. Optional systemd/Docker
service integration (`start/stop/restart`) is the next phase and must reuse
each repo's existing deployment architecture, never invent a conflicting one.
