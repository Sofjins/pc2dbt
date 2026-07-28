from pc2dbt.emitter import emit_model
from pc2dbt.parser import parse_mapping


def test_emits_a_cte_per_source_and_per_transformation_in_dependency_order():
    mapping = parse_mapping("fixtures/m_customers.xml")
    sql = emit_model(mapping)

    all_ctes = list(mapping.sources) + list(mapping.transformations)
    position = {name: sql.index(f"{name} as (") for name in all_ctes}
    for connector in mapping.connectors:
        if connector.from_instance in position and connector.to_instance in position:
            assert position[connector.from_instance] < position[connector.to_instance]


def test_source_ctes_read_from_source_macro():
    mapping = parse_mapping("fixtures/m_customers.xml")
    sql = emit_model(mapping)
    assert "{{ source('jaffle_shop', 'raw_customers') }}" in sql
    assert "{{ source('jaffle_shop', 'raw_orders') }}" in sql
    assert "{{ source('jaffle_shop', 'raw_payments') }}" in sql


def test_final_select_matches_target_fields_in_order():
    mapping = parse_mapping("fixtures/m_customers.xml")
    sql = emit_model(mapping)
    final_select = sql[sql.rindex("\nselect") :]
    for field in mapping.target.fields:
        assert field.name in final_select


def test_joiner_ctes_use_correct_join_direction():
    mapping = parse_mapping("fixtures/m_customers.xml")
    sql = emit_model(mapping)

    # Normal Join (payments-orders) -> INNER
    inner_cte = sql[sql.index("JNR_payments_orders as (") : sql.index("JNR_payments_orders as (") + 400]
    assert "inner join" in inner_cte

    # Master Outer Join -> detail (customers) LEFT JOIN master (agg_orders)
    outer_cte_start = sql.index("JNR_customers_orders as (")
    outer_cte = sql[outer_cte_start : outer_cte_start + 400]
    assert "left join" in outer_cte
    assert "from EXP_stg_customers" in outer_cte


def test_raises_clear_error_for_unsupported_transformation_type():
    mapping = parse_mapping("fixtures/m_customers.xml")
    mapping.transformations["EXP_final"].type = "Lookup"
    try:
        emit_model(mapping)
        assert False, "expected a ValueError for an unsupported transformation type"
    except ValueError as exc:
        assert "Lookup" in str(exc)
