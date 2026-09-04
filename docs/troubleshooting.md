# Troubleshooting

## `setup` reports SKIPPED / UNAVAILABLE

- `UNAVAILABLE`: a base tool is missing (`node`, `git`, `docker`). Install it
  or ignore the module if you don't need it.
- `SKIPPED`: dry-run, already `READY` (idempotent), or a conservative v0.2
  remote-install deferral (no network side effects). Re-run with `--dry-run`
  to see the reason.

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
  logged (shows `[REDACTED]`).
- `setup --all` (not `--public`) is required to include optional modules.

## JSON looks broken

Machine mode prints valid JSON on stdout only; Rich tables/diagnostics go to
stderr or are suppressed. Use `--json` and parse stdout alone.

## Clean removed nothing / refuses

By design: only `~/.sklab`-owned `*.tmp/*.log/*.cache` + `~/.sklab/tmp` are
candidates. User repos and run history are never touched. Use `--dry-run` to
preview.
