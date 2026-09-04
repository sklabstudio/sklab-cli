# Security (v0.3 regression suite)

Mandatory, enforced by code + tests (`tests/unit/test_v03.py` plus v0.2 suite):

- Command injection: argv arrays only; metacharacter args stay literal
  (tested with `'; rm -rf /'` payloads); string shell commands rejected.
- Malicious manifest command arguments: `install.command`/`health.command`
  must be non-empty argv arrays; traversal ids (`../`) rejected;
  `safe_module_dir` blocks root escapes.
- Unsafe path traversal / symlink escape: writes confined to SKLab-owned
  roots; `uninstall` only removes owned markers/venvs/checkouts, never user
  repos (tested with symlinked sources + precious-file guards).
- Secret redaction: tokens, passwords, auth headers, private credentials,
  private URLs with credentials (`redaction.py` + run-log redaction).
- `PUBLIC → PRIVATE` dependency rejection (resolver `VISIBILITY_VIOLATION`).
- Private manifest leakage: local-only, never uploaded/logged verbatim, no
  tokens in state or CI (mocked auth in public CI).
- Accidental `shell=True`: AST scan over `src/` (documentation mentions don't
  count; actual `shell=True` kwargs do).
- Arbitrary sudo/system mutation without approval: no hidden sudo/apt;
  apt/PATH/service changes only after explicit confirmation (`--yes` /
  `--fix-path`), never from dry-run/status/doctor.
- Never downloads and executes unsigned arbitrary shell scripts silently
  (Node 20 guidance is documentation only; no `curl|bash` runs).
- No `shell=True` anywhere; no `curl|bash` hooks; no credential scraping of
  any kind; no automatic mainnet/blockchain actions; no destructive cleanup.
- Machine output is valid JSON on stdout only; diagnostics go to stderr.
- No telemetry of any kind.
- Health/install subprocesses use argv arrays with timeouts and output caps.
