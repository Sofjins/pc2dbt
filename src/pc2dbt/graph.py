"""Builds the instance DAG from a Mapping and returns a topological order."""

import graphlib

from pc2dbt.ir import Mapping


def topological_order(mapping: Mapping) -> list[str]:
    """Return instance names in an order where every instance appears after
    all instances that feed into it. Raises graphlib.CycleError if the
    mapping's connectors form a cycle."""
    dependencies: dict[str, set[str]] = {instance.name: set() for instance in mapping.instances}
    for connector in mapping.connectors:
        dependencies[connector.to_instance].add(connector.from_instance)

    return list(graphlib.TopologicalSorter(dependencies).static_order())
