# Repository Instructions

## Purpose

Provide stable project, doctor, workstation, release, and automation workflows from the command line.

## Read before editing

- `src/sklab/` for commands and public output
- `tests/` for exit-code and JSON contracts
- `README.md` for supported versus planned commands

## Working rules

- Work only inside this repository unless the user explicitly requests a coordinated cross-repository change.
- Read `README.md`, the package manifest, and the relevant CI workflow before changing behavior.
- Preserve unrelated user changes. Do not rewrite or delete work merely to make a patch cleaner.
- Never commit credentials, tokens, client data, local state, caches, build output, or generated secrets.
- Do not describe a configured, mocked, or importable integration as successfully executed.
- When behavior or a public contract changes, update tests and user-facing documentation in the same change.
- Keep documented commands, JSON fields, and exit codes backward-compatible or version the change.
- Diagnostic commands must be read-only unless mutation is explicitly selected and confirmed.
- Never expose credentials in terminal output, JSON, logs, or error messages.

## Verification

- `ruff check .`
- `mypy src/sklab`
- `python -m pytest`
- `python -m build`
- Install the wheel and smoke-test the documented CLI entry points.

If an environment-dependent check cannot run, state exactly what was skipped and
why. Do not replace a missing check with a claim of success.

## Completion checklist

- The smallest correct change is implemented within this repository's scope.
- New or changed behavior has focused tests.
- Public interfaces, examples, and limitations are documented.
- Security and credential boundaries still hold.
- `git diff --check` passes and the working tree contains no unintended files.
