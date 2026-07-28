"""Builds the instance DAG from a Mapping and returns a topological order."""

from pc2dbt.ir import Mapping


def topological_order(mapping: Mapping) -> list[str]:
    """Return instance names in an order where every instance appears after
    all instances that feed into it."""
    raise NotImplementedError
