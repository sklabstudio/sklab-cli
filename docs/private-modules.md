# Private modules

PUBLIC stays PUBLIC. PRIVATE stays PRIVATE.

The public CLI knows how to load an **optional local/private manifest**
generically but never contains private source, credentials, or proprietary
implementation, and never requires private modules for normal public operation.

## Registering

```yaml
# /secure/path/module.yaml (stays local, never uploaded)
schema_version: 1
id: private-module
name: Private Module
visibility: private
source:
  type: git
  url_env: SKLAB_PRIVATE_MODULE_URL
install:
  type: local
  path: /secure/checkout/private-module
health:
  command: ["private-module", "--version"]
dependencies: [agent-adapters]  # PRIVATE -> PUBLIC is allowed
```

```sh
export SKLAB_PRIVATE_MODULE_URL="https://<token>@example.com/org/private.git"
sklab modules add-manifest /secure/path/module.yaml
sklab module install private-module
sklab module doctor private-module
sklab setup --all --dry-run   # includes it when accessible
```

Known private modules (examples, never embedded in public descriptors):

```text
~/.sklab/modules.d/appsec-lab.yaml
~/.sklab/modules.d/protocol-intelligence.yaml
```

Behavior: manifest present → validate, resolve deps, verify authenticated
access (`gh auth status` / credential helper), install on `--all`. Manifest
absent → module simply unregistered. Auth missing → `AUTH_REQUIRED` (public
install continues, no crash). Never ask for tokens in logs; never store GitHub
tokens in SKLab state; never print tokens.

Rules:

- The manifest remains local (`~/.sklab/modules.d/`); the CLI never uploads it.
- Source credentials come from the environment / git credential helper, never
  from inline secrets. Logs redact URLs/tokens (`[REDACTED]`).
- A private module may depend on public modules.
- A public module must **NOT** depend on a private module (resolver rejects
  `VISIBILITY_VIOLATION`).

Allowed: `PRIVATE → PUBLIC`, `PUBLIC → PUBLIC`. Forbidden: `PUBLIC → PRIVATE`.

## Visibility boundary

- Built-in registry is public-only (audited by `test_builtin_registry_public_only`).
- `sklab status --json` shows `visibility` and `origin` per module without
  exposing private source details.
- No telemetry exists to leak anything.
