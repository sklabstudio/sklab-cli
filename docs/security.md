# Security

Mandatory, enforced by code + tests:

- No `shell=True` anywhere (`test_no_shell_true_in_codebase` parses the AST).
- No `curl|bash`, no arbitrary remote install hooks. Manifest commands must be
  structured argv arrays; string shell commands are rejected at validation.
- No hidden `sudo`: installers never escalate; missing privileges are reported.
- No credential scraping, browser-cookie scraping, provider session-token
  scraping, or secret logging. `redaction.py` masks `token=/secret:/password=`,
  `Bearer …`, `https://user:pass@…`, known token prefixes (`sk-`, `ghp_`,
  `gho_`, `github_pat_`, `xox*`), `?token=…`, and secret env values.
- No public/private code mixing: builtin registry is public-only, no private
  URLs (`@`, `token`) in descriptors.
- No automatic mainnet/blockchain actions; no destructive filesystem cleanup
  (`clean` only touches `~/.sklab`-owned temp; user repos/history preserved).
- Machine output is valid JSON on stdout only; diagnostics go to stderr.
- No telemetry of any kind.
- Health/install subprocesses use argv arrays with timeouts and output caps.
