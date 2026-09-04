# VPS

Target: a fresh Ubuntu VPS should converge with:

```sh
pip install sklab-cli
sklab setup --all --dry-run
sklab setup --all --yes
sklab doctor --stack
```

Priorities: Linux/Ubuntu VPS + desktop first; Windows/macOS detection works
where practical without faking parity.

This session deliberately does **NOT** provision host firewall, DNS, TLS,
Tailscale, or Cloudflare automatically — those remain explicit deployment
steps.

Web UI (if installed): the CLI detects frontend/backend health and shows the
local URL without exposing it publicly, changing firewalls, or creating DNS
records.
