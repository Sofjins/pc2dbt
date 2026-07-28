"""Builds the instance DAG from a Mapping and returns a topological order."""

from pc2dbt.ir import Mapping


def topological_order(mapping: Mapping) -> list[str]:
    """Return instance names in an order where every instance appears after
    all instances that feed into it (depth-first post-order)."""
    dependencies: dict[str, set[str]] = {instance.name: set() for instance in mapping.instances}
    for connector in mapping.connectors:
        dependencies[connector.to_instance].add(connector.from_instance)

    ordered: list[str] = []
    visited: set[str] = set()
    in_progress: set[str] = set()

    def visit(name: str) -> None:
        if name in visited:
            return
        if name in in_progress:
            raise ValueError(f"Cycle detected in mapping instance graph at {name!r}")
        in_progress.add(name)
        for upstream_name in sorted(dependencies[name]):
            visit(upstream_name)
        in_progress.discard(name)
        visited.add(name)
        ordered.append(name)

    for instance in mapping.instances:
        visit(instance.name)

    return ordered
