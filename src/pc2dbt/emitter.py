"""Walks the mapping's DAG and assembles the final dbt SQL model text."""

import textwrap

from pc2dbt.generators import (
    PortSources,
    column_reference,
    generate_aggregator,
    generate_joiner,
    generate_projection,
    generate_source_import,
    single_upstream_alias,
)
from pc2dbt.graph import topological_order
from pc2dbt.ir import Connector, Instance, Mapping

_GENERATORS = {
    "Source Qualifier": generate_projection,
    "Expression": generate_projection,
    "Aggregator": generate_aggregator,
    "Joiner": generate_joiner,
}


def emit_model(mapping: Mapping) -> str:
    instances_by_name = {instance.name: instance for instance in mapping.instances}
    incoming_by_target = _index_connectors_by_target(mapping.connectors)

    target_instance = next(i for i in mapping.instances if i.type == "TARGET")

    cte_blocks = []
    for instance_name in topological_order(mapping):
        instance = instances_by_name[instance_name]
        if instance.type == "SOURCE":
            body = generate_source_import(mapping.sources[instance.transformation_name], mapping.source_group)
        elif instance.type == "TARGET":
            continue
        else:
            body = _generate_transformation_cte(mapping, instance, incoming_by_target)
        cte_blocks.append(f"{instance.name} as (\n\n{textwrap.indent(body, '    ')}\n\n)")

    final_select = _build_final_select(mapping, target_instance, incoming_by_target)

    return "with " + ",\n\n".join(cte_blocks) + "\n\n" + final_select


def _generate_transformation_cte(mapping: Mapping, instance: Instance, incoming_by_target: dict) -> str:
    transformation = mapping.transformations[instance.transformation_name]
    generator = _GENERATORS.get(transformation.type)
    if generator is None:
        raise ValueError(f"Unsupported transformation type: {transformation.type!r}")

    port_sources = _port_sources_for(instance.name, incoming_by_target)
    return generator(transformation, port_sources)


def _port_sources_for(instance_name: str, incoming_by_target: dict) -> PortSources:
    connectors = incoming_by_target.get(instance_name, [])
    return {c.to_field: (c.from_instance, c.from_field) for c in connectors}


def _build_final_select(mapping: Mapping, target_instance: Instance, incoming_by_target: dict) -> str:
    port_sources = _port_sources_for(target_instance.name, incoming_by_target)
    upstream_alias = single_upstream_alias(port_sources)

    select_cols = []
    for target_field in mapping.target.fields:
        _, column = port_sources[target_field.name]
        select_cols.append(column_reference(column, target_field.name))

    select_clause = ",\n    ".join(select_cols)
    return f"select\n    {select_clause}\nfrom {upstream_alias}"


def _index_connectors_by_target(connectors: list[Connector]) -> dict[str, list[Connector]]:
    index: dict[str, list[Connector]] = {}
    for connector in connectors:
        index.setdefault(connector.to_instance, []).append(connector)
    return index
