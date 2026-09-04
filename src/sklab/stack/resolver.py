"""Dependency graph: stable ordering, cycle/missing/version/visibility checks."""

from __future__ import annotations

from dataclasses import dataclass, field

from sklab.stack.registry import Registry


class ResolverError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


CYCLE = "DEPENDENCY_CYCLE"
MISSING = "MISSING_DEPENDENCY"
INCOMPATIBLE = "INCOMPATIBLE_VERSION"
VISIBILITY = "VISIBILITY_VIOLATION"
UNAVAILABLE = "UNAVAILABLE_MODULE"


@dataclass
class ResolveResult:
    order: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _version_satisfies(installed: str, constraint: str | None) -> bool:
    if not constraint:
        return True
    text = constraint.strip()
    if text in ("*", "any"):
        return True
    if text.startswith(">="):
        want = text[2:].strip()
        return _compare_versions(installed, want) >= 0
    if text.startswith("=="):
        want = text[2:].strip()
        return installed.strip() == want
    # Bare version means exact match in v0.2 (conservative).
    return installed.strip() == text


def _compare_versions(left: str, right: str) -> int:
    def parts(value: str) -> list[object]:
        out: list[object] = []
        for chunk in value.strip().split("."):
            out.append(int(chunk) if chunk.isdigit() else chunk)
        return out

    lparts, rparts = parts(left), parts(right)
    if lparts == rparts:
        return 0
    return -1 if str(lparts) < str(rparts) else 1


def resolve(
    registry: Registry,
    selected: list[str] | None = None,
    *,
    include_optional: bool = False,
) -> ResolveResult:
    """Topologically sort modules. Stable (alphabetical) ordering.

    Raises ResolverError on cycles, missing deps, version conflicts, or
    PUBLIC -> PRIVATE visibility violations.
    """
    modules = registry.modules
    if selected is None:
        wanted = sorted(modules.keys())
    else:
        wanted = list(selected)
        for module_id in wanted:
            if module_id not in modules:
                raise ResolverError(MISSING, f"Unknown module: {module_id}.")

    # Closure over required (+ optional when requested) dependencies.
    closure: set[str] = set(wanted)
    queue = sorted(wanted)
    while queue:
        current = queue.pop(0)
        loaded = modules[current]
        manifest = loaded.manifest
        deps = list(manifest.dependencies)
        if include_optional:
            deps = deps + list(manifest.optional_dependencies)
        for dep in deps:
            # Visibility rule: PUBLIC -> PRIVATE is forbidden (mandatory).
            target = modules.get(dep.id)
            if target is not None:
                if manifest.visibility == "public" and target.manifest.visibility == "private":
                    raise ResolverError(
                        VISIBILITY,
                        f"Visibility violation: public module '{manifest.id}' must not depend on "
                        f"private module '{dep.id}'. Reverse the direction (PRIVATE -> PUBLIC).",
                    )
            if dep.id not in modules:
                if dep.optional:
                    continue
                raise ResolverError(
                    MISSING, f"Module '{current}' requires missing module '{dep.id}'."
                )
            if dep.id not in closure:
                closure.add(dep.id)
                queue.append(dep.id)
        queue.sort()

    # Version checks within the closure.
    for module_id in sorted(closure):
        manifest = modules[module_id].manifest
        for dep in list(manifest.dependencies) + list(manifest.optional_dependencies):
            if dep.id not in closure or dep.version is None:
                continue
            installed_version = modules[dep.id].manifest.version
            if not _version_satisfies(installed_version, dep.version):
                raise ResolverError(
                    INCOMPATIBLE,
                    f"Module '{module_id}' needs '{dep.id}' version '{dep.version}' "
                    f"but '{installed_version}' is configured.",
                )

    # Kahn's algorithm with alphabetical stability.
    edges: dict[str, set[str]] = {mid: set() for mid in closure}
    indegree: dict[str, int] = dict.fromkeys(closure, 0)
    for module_id in closure:
        manifest = modules[module_id].manifest
        for dep in list(manifest.dependencies) + (
            list(manifest.optional_dependencies) if include_optional else []
        ):
            if dep.id in closure and dep.id != module_id:
                if module_id not in edges[dep.id]:
                    edges[dep.id].add(module_id)
                    indegree[module_id] += 1

    ready = sorted([mid for mid, deg in indegree.items() if deg == 0])
    order: list[str] = []
    while ready:
        current = ready.pop(0)
        order.append(current)
        for dependent in sorted(edges[current]):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)
        ready.sort()

    if len(order) != len(closure):
        remaining = sorted(set(closure) - set(order))
        raise ResolverError(CYCLE, f"Dependency cycle detected among: {', '.join(remaining)}.")
    return ResolveResult(order=order)
