# VPS (v0.3 one-command bootstrap)

Target profile: fresh **Ubuntu 24.04 LTS x86_64**, minimum **2 vCPU / ~4 GB RAM /
4+ GB swap / ~80 GB disk**. 16 GB is the recommended full workstation; 4 GB is
the supported test minimum (heavy modules install fine but must run
sequentially — Playwright/Chromium, Solidity fuzzing, protocol simulation,
large Docker builds).

## The one command

```sh
pipx install "git+https://github.com/sklabstudio/sklab-cli.git"
sklab setup --all --dry-run
sklab setup --all
sklab status
sklab doctor --stack
```

Upgrading an existing Git-installed v0.2 checkout on the VPS:

```sh
cd ~/sklab-cli
git pull --ff-only
pipx install .
sklab setup --all --dry-run
sklab setup --all --yes
sklab status
sklab doctor --stack
```

What to expect:

- First `setup --all` (after confirmation) clones public repos into
  `/opt/sklab/repos` (root) or `~/.local/share/sklab/repos`, builds venvs and
  frontend assets, and writes markers + redacted logs.
- `/root/.local/bin is not on PATH` is detected; re-run/confirm with
  `--fix-path` (or `--yes`) for the idempotent shell fix, then re-login.
- Second `setup --all` reports `READY / SKIPPED / NO_CHANGE` — no duplicate
  clones, venvs, services, manifests, PATH lines, or config.
- Fresh VPS without private manifests installs the public stack fully; no
  AppSec/Protocol source required. With authenticated local manifests
  (`~/.sklab/modules.d/appsec-lab.yaml`,
  `~/.sklab/modules.d/protocol-intelligence.yaml` + `gh auth login`),
  `--all` resolves and installs them too.

Priorities: Linux/Ubuntu VPS + desktop first; Windows/macOS detection works
where practical without faking parity.

Explicitly NOT automatic: host firewall, DNS, TLS, Tailscale, Cloudflare,
public port exposure, production DNS records. The Web UI binds
localhost/private-safe by default; service definitions may be prepared but
ports are never opened by the installer.

## Fresh-VPS acceptance (what v0.3 verified)

- `setup --all --dry-run`: zero mutation (no clone/fetch/install/docker/apt/
  PATH/service), exact plan printed.
- `setup --all`: public modules actually install (no v0.2 conservative skip).
- Immediate second `setup --all`: idempotent, no duplicates.
- Private-absent: public stack succeeds. Private-present (mocked auth in CI):
  private modules resolve/install without public leakage.
- Web UI smoke: backend imports, frontend build path, health endpoint wiring,
  module discovery — without public exposure.
- `doctor --stack`: PATH problems, Docker daemon states, Node 18 guidance,
  and resource limits reported honestly; no false READY.
