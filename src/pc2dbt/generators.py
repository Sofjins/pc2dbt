"""Per-transformation-type SQL fragment generation.

Each function builds the SELECT/FROM/JOIN/GROUP BY body for one
transformation's CTE. `port_sources` is a dict mapping a local port name to
the (upstream_cte_alias, upstream_column_name) that feeds it - it is built
by emitter.py by walking the mapping's connectors, so generators never touch
XML or do topological sorting themselves.
"""

import re

from pc2dbt.ir import Source, Transformation

PortSources = dict[str, tuple[str, str]]


def generate_source_import(source: Source, source_group: str) -> str:
    """Leaf CTE body: selects a raw source table's columns from a dbt source()."""
    columns = ",\n    ".join(f.name for f in source.fields)
    source_ref = "{{ source('%s', '%s') }}" % (source_group, source.name)
    return f"select\n    {columns}\nfrom {source_ref}"


def generate_projection(transformation: Transformation, port_sources: PortSources) -> str:
    """CTE body for a Source Qualifier or Expression transformation: a single
    upstream CTE, passthrough columns for INPUT/OUTPUT ports, computed
    expressions for OUTPUT ports."""
    upstream_alias = _single_upstream_alias(port_sources)
    select_cols = [
        _select_expression(port, transformation, port_sources)
        for port in transformation.ports
        if port.porttype != "INPUT"
    ]
    select_clause = ",\n    ".join(select_cols)
    return f"select\n    {select_clause}\nfrom {upstream_alias}"


def generate_aggregator(transformation: Transformation, port_sources: PortSources) -> str:
    """CTE body for an Aggregator: GROUP BY ports plus aggregate expressions,
    over a single upstream CTE."""
    upstream_alias = _single_upstream_alias(port_sources)
    select_cols = []
    group_by_cols = []
    for port in transformation.ports:
        if port.expression_type == "GROUPBY":
            _, column = port_sources[port.name]
            select_cols.append(_passthrough_expression(port.name, column))
            group_by_cols.append(column)
        elif port.porttype == "OUTPUT" and port.expression:
            expr_sql = _substitute_local_refs(port.expression, port_sources)
            select_cols.append(f"{expr_sql} as {port.name}")
        # pure INPUT ports that aren't GROUPBY are only used inside aggregate
        # expressions above, so they are not projected on their own.

    select_clause = ",\n    ".join(select_cols)
    group_by_clause = ", ".join(group_by_cols)
    return f"select\n    {select_clause}\nfrom {upstream_alias}\ngroup by {group_by_clause}"


def generate_joiner(transformation: Transformation, port_sources: PortSources) -> str:
    """CTE body for a Joiner: two upstream CTEs, joined per the "Join Type"
    and "Join Condition" table attributes, with the "Master Ports" attribute
    identifying which upstream is the master side."""
    join_type = transformation.table_attributes["Join Type"]
    condition = transformation.table_attributes["Join Condition"]
    master_port_names = transformation.table_attributes["Master Ports"].split(",")

    master_alias, _ = port_sources[master_port_names[0]]
    all_aliases = {alias for alias, _ in port_sources.values()}
    detail_alias = next(alias for alias in all_aliases if alias != master_alias)

    on_clause = _translate_join_condition(condition, port_sources)

    select_cols = []
    for port in transformation.ports:
        if port.porttype != "INPUT/OUTPUT":
            continue
        alias, column = port_sources[port.name]
        if column == port.name:
            select_cols.append(f"{alias}.{column}")
        else:
            select_cols.append(f"{alias}.{column} as {port.name}")
    select_clause = ",\n    ".join(select_cols)

    if join_type == "Normal Join":
        from_alias, join_alias, sql_join_type = master_alias, detail_alias, "inner join"
    elif join_type == "Master Outer Join":
        from_alias, join_alias, sql_join_type = detail_alias, master_alias, "left join"
    else:
        raise ValueError(f"Unsupported Joiner Join Type: {join_type!r}")

    return (
        f"select\n    {select_clause}\n"
        f"from {from_alias}\n"
        f"{sql_join_type} {join_alias}\n"
        f"    on {on_clause}"
    )


def _select_expression(port, transformation: Transformation, port_sources: PortSources) -> str:
    if port.porttype == "OUTPUT" and port.expression:
        expr_sql = _substitute_local_refs(port.expression, port_sources)
        return f"{expr_sql} as {port.name}"
    _, column = port_sources[port.name]
    return _passthrough_expression(port.name, column)


def _passthrough_expression(port_name: str, upstream_column: str) -> str:
    if upstream_column == port_name:
        return port_name
    return f"{upstream_column} as {port_name}"


def _translate_join_condition(condition: str, port_sources: PortSources) -> str:
    left_name, right_name = (part.strip() for part in condition.split("="))
    left_alias, left_column = port_sources[left_name]
    right_alias, right_column = port_sources[right_name]
    return f"{left_alias}.{left_column} = {right_alias}.{right_column}"


def _substitute_local_refs(expression: str, port_sources: PortSources) -> str:
    """Replace local port names referenced in an expression with the
    upstream column that actually holds that value."""
    for local_name in sorted(port_sources, key=len, reverse=True):
        _, column = port_sources[local_name]
        expression = re.sub(rf"\b{re.escape(local_name)}\b", column, expression)
    return expression


def _single_upstream_alias(port_sources: PortSources) -> str:
    return next(iter(port_sources.values()))[0]
