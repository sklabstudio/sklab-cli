# Troubleshooting

## `setup` reports SKIPPED / UNAVAILABLE / AUTH_REQUIRED

- `UNAVAILABLE`: a base tool is missing (`node`, `git`, `docker`). Install it
  or ignore the module if you don't need it.
- `SKIPPED`: dry-run, or already `READY` (idempotent). Re-run with `--dry-run`
  to see the reason.
- `AUTH_REQUIRED`: a private module needs credentials. Run `gh auth login`
  (or export its `url_env`), then re-run `sklab setup --all` to resume.
  Public modules are unaffected.
- `LOW_DISK`: free space and re-run. The installer aborts before partial
  installation and never deletes unrelated files.

## Resume after failure

Re-run `sklab setup --all`. Successes are preserved and skipped; only failed
or pending modules are retried. The summary prints exactly which modules need
attention plus the redacted log path (`logs/setup-*.log`).

## Dependency errors

- `DEPENDENCY_CYCLE …`: two manifests depend on each other. Break the cycle.
- `MISSING_DEPENDENCY …`: a required id is not in the builtin registry nor
  `~/.sklab/modules.d/`. Add the missing manifest or remove the edge.
- `VISIBILITY_VIOLATION …`: a public module depends on a private one.
  Reverse the direction (`PRIVATE → PUBLIC`).
- `INCOMPATIBLE_VERSION …`: pin or upgrade the dependency.

## Health is NOT_INSTALLED but I just installed

`doctor --stack` re-inspects reality; the state file is advisory. Check that
the module's `health.command[0]` is on `PATH` (`shutil.which`) and runs with
exit 0. Exit 1 means `DEGRADED`, other non-zero means `FAILED`.

## Private module won't attach

- Ensure the file validates: `sklab modules add-manifest <file>`.
- `source.url_env` must name an existing env var; the value itself is never
  logged (shows `[REDACTED]`). Never paste tokens into logs.
- `setup --all` (not `--public`) is required to include optional modules.
- `appsec-lab` / `protocol-intelligence` stay local-only; they are never in
  the public registry and never needed for the public stack.

## PATH: `~/.local/bin is not on PATH`

Re-run setup with `--fix-path` (or `--yes`) for the idempotent one-line shell
fix, then re-login (or `source ~/.bashrc`). `doctor --stack` verifies.

## Node 18 on fresh VPS

Node 18 reports DEGRADED with upgrade guidance (Node 20 LTS recommended).
The installer never runs `curl|bash` automatically; follow `docs/vps.md`.

## Docker states

`READY` / `DAEMON_UNAVAILABLE` (start dockerd) / `NOT_INSTALLED` /
`PERMISSION_DENIED` (add your user to the `docker` group). Modules that do
not need Docker never require it.

## JSON looks broken

Machine mode prints valid JSON on stdout only; Rich tables/diagnostics go to
stderr or are suppressed. Use `--json` and parse stdout alone.

## Clean removed nothing / refuses

By design: only `~/.sklab`-owned `*.tmp/*.log/*.cache` + `~/.sklab/tmp` are
candidates. User repos and run history are never touched. Use `--dry-run` to
preview.
