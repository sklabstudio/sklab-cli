# Modules

## Manifest (schema_version 1, strict)

```yaml
schema_version: 1
id: orchestrator
name: SKLab Orchestrator
version: 0.1.0
visibility: public  # public | private
source:
  type: git
  repository: sklabstudio/orchestrator
  # url_env: SKLAB_PRIVATE_MODULE_URL  # private indirection (no secrets inline)
install:
  type: python  # python|node|git|docker-compose|command|local (+ ALIASES)
  package_path: .
health:
  command: ["sklab-run", "doctor", "--json"]  # argv array only
  timeout: 15.0
capabilities: [orchestration]
dependencies: [agent-adapters, provider-connections]
optional_dependencies: []
config_paths: []
env_required: []
service: {}
web_ui: {}
```

Validation: unknown fields rejected, `id` must match `^[a-z0-9][a-z0-9-]{1,62}$`,
`install.command` / `health.command` must be non-empty argv arrays,
`source` needs one of `repository|url|url_env|package|path`.

Install aliases accepted: `PYTHON_PACKAGE→python`, `NODE_PACKAGE→node`,
`GIT_SOURCE→git`, `DOCKER_COMPOSE→docker-compose`, `COMMAND→command`,
`LOCAL_PATH→local`.

## Registry

- Built-in: 16 public descriptors (RepoContext, Coding Lab, Starters, SKLab CLI,
  PatchBench, CodeTrials, PromptBench, BenchSuite, ReproBox, Agent Adapters,
  Provider Connections, Orchestrator, Web UI, Skill Hub, Cyber Pack,
  Contract Toolkit). Generic git pointers only — no code, no credentials.
- Local overlay: `~/.sklab/modules.d/*.yaml` (`SKLAB_MODULES_DIR` overrides).
  This is the extension point for optional/private modules. Files are validated
  strictly; one bad file never breaks the registry (recorded in `errors`).
- `sklab modules` lists merged public + local. `sklab modules --json` is
  machine-readable. `sklab modules add-manifest <file>` (also
  `sklab module add-manifest`) copies a validated manifest into `modules.d`.

## Capabilities

`orchestration, web-ui, skills, security, contracts, benchmarking, sandbox,`
`verification, agents, providers, repo-context` (generic strings; custom
lowercase-hyphen values allowed).

## Health model

`READY` (exit 0 / executable found / marker present), `DEGRADED` (exit 1),
`FAILED` (other non-zero), `NOT_INSTALLED` (binary/marker missing),
`UNAVAILABLE` (base tool missing), `UNKNOWN` (timeout/ambiguous).
`sklab status` and `sklab doctor --stack` never fake `READY`.
