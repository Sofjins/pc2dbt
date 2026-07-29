import pytest

from pc2dbt.generators import (
    UpstreamColumn,
    generate_aggregator,
    generate_joiner,
    generate_projection,
    generate_source_import,
)
from pc2dbt.ir import Port, Source, Field, Transformation


def test_generate_source_import():
    source = Source(
        name="raw_customers",
        fields=[Field(name="ID", datatype="integer"), Field(name="FIRST_NAME", datatype="string")],
    )
    sql = generate_source_import(source, source_group="jaffle_shop")
    assert "select" in sql
    assert "ID" in sql and "FIRST_NAME" in sql
    assert "{{ source('jaffle_shop', 'raw_customers') }}" in sql


def test_generate_projection_passthrough_source_qualifier():
    sq = Transformation(
        name="SQ_raw_customers",
        type="Source Qualifier",
        ports=[
            Port(name="ID", datatype="integer", porttype="INPUT/OUTPUT"),
            Port(name="FIRST_NAME", datatype="string", porttype="INPUT/OUTPUT"),
        ],
    )
    port_sources = {
        "ID": UpstreamColumn("raw_customers", "ID"),
        "FIRST_NAME": UpstreamColumn("raw_customers", "FIRST_NAME"),
    }
    sql = generate_projection(sq, port_sources)
    assert "select" in sql
    assert "ID" in sql
    assert "FIRST_NAME" in sql
    assert "from raw_customers" in sql


def test_generate_projection_expression_with_rename_and_computation():
    exp = Transformation(
        name="EXP_stg_payments",
        type="Expression",
        ports=[
            Port(name="ID", datatype="integer", porttype="INPUT"),
            Port(name="ORDER_ID", datatype="integer", porttype="INPUT/OUTPUT"),
            Port(name="AMOUNT_CENTS", datatype="decimal", porttype="INPUT"),
            Port(
                name="PAYMENT_ID",
                datatype="integer",
                porttype="OUTPUT",
                expression="ID",
                expression_type="GENERAL",
            ),
            Port(
                name="AMOUNT",
                datatype="decimal",
                porttype="OUTPUT",
                expression="AMOUNT_CENTS / 100",
                expression_type="GENERAL",
            ),
        ],
    )
    port_sources = {
        "ID": UpstreamColumn("sq_raw_payments", "ID"),
        "ORDER_ID": UpstreamColumn("sq_raw_payments", "ORDER_ID"),
        "AMOUNT_CENTS": UpstreamColumn("sq_raw_payments", "AMOUNT"),
    }
    sql = generate_projection(exp, port_sources)
    assert "ID as PAYMENT_ID" in sql
    assert "AMOUNT / 100 as AMOUNT" in sql
    assert "ORDER_ID" in sql
    # pure INPUT port ID is consumed by PAYMENT_ID's expression, not itself
    # projected as a standalone column
    select_columns = [line.strip().rstrip(",") for line in sql.splitlines()]
    assert "ID" not in select_columns
    assert "from sq_raw_payments" in sql


def test_generate_aggregator():
    agg = Transformation(
        name="AGG_customer_orders",
        type="Aggregator",
        ports=[
            Port(name="CUSTOMER_ID", datatype="integer", porttype="INPUT/OUTPUT", expression_type="GROUPBY"),
            Port(name="ORDER_DATE", datatype="date/time", porttype="INPUT"),
            Port(name="ORDER_ID", datatype="integer", porttype="INPUT"),
            Port(
                name="FIRST_ORDER",
                datatype="date/time",
                porttype="OUTPUT",
                expression="MIN(ORDER_DATE)",
                expression_type="GENERAL",
            ),
            Port(
                name="NUMBER_OF_ORDERS",
                datatype="integer",
                porttype="OUTPUT",
                expression="COUNT(ORDER_ID)",
                expression_type="GENERAL",
            ),
        ],
    )
    port_sources = {
        "CUSTOMER_ID": UpstreamColumn("exp_stg_orders", "CUSTOMER_ID"),
        "ORDER_DATE": UpstreamColumn("exp_stg_orders", "ORDER_DATE"),
        "ORDER_ID": UpstreamColumn("exp_stg_orders", "ORDER_ID"),
    }
    sql = generate_aggregator(agg, port_sources)
    assert "MIN(ORDER_DATE) as FIRST_ORDER" in sql
    assert "COUNT(ORDER_ID) as NUMBER_OF_ORDERS" in sql
    assert "from exp_stg_orders" in sql
    assert "group by CUSTOMER_ID" in sql


def test_generate_joiner_normal_join_is_inner():
    joiner = Transformation(
        name="JNR_payments_orders",
        type="Joiner",
        ports=[
            Port(name="ORDER_ID", datatype="integer", porttype="INPUT/OUTPUT"),
            Port(name="CUSTOMER_ID", datatype="integer", porttype="INPUT/OUTPUT"),
            Port(name="ORDER_ID1", datatype="integer", porttype="INPUT"),
            Port(name="AMOUNT", datatype="decimal", porttype="INPUT/OUTPUT"),
        ],
        table_attributes={
            "Join Condition": "ORDER_ID = ORDER_ID1",
            "Join Type": "Normal Join",
            "Master Ports": "ORDER_ID,CUSTOMER_ID",
        },
    )
    port_sources = {
        "ORDER_ID": UpstreamColumn("exp_stg_orders", "ORDER_ID"),
        "CUSTOMER_ID": UpstreamColumn("exp_stg_orders", "CUSTOMER_ID"),
        "ORDER_ID1": UpstreamColumn("exp_stg_payments", "ORDER_ID"),
        "AMOUNT": UpstreamColumn("exp_stg_payments", "AMOUNT"),
    }
    sql = generate_joiner(joiner, port_sources)
    assert "inner join" in sql
    assert "exp_stg_orders.ORDER_ID = exp_stg_payments.ORDER_ID" in sql
    assert "exp_stg_payments.AMOUNT" in sql
    # pure INPUT join-key port is not projected
    assert "ORDER_ID1" not in sql.split("from")[0]


def test_generate_joiner_master_outer_join_keeps_detail_side():
    joiner = Transformation(
        name="JNR_customers_orders",
        type="Joiner",
        ports=[
            Port(name="CUSTOMER_ID", datatype="integer", porttype="INPUT/OUTPUT"),
            Port(name="FIRST_ORDER", datatype="date/time", porttype="INPUT/OUTPUT"),
            Port(name="CUSTOMER_ID1", datatype="integer", porttype="INPUT/OUTPUT"),
            Port(name="FIRST_NAME", datatype="string", porttype="INPUT/OUTPUT"),
        ],
        table_attributes={
            "Join Condition": "CUSTOMER_ID = CUSTOMER_ID1",
            "Join Type": "Master Outer Join",
            "Master Ports": "CUSTOMER_ID,FIRST_ORDER",
        },
    )
    port_sources = {
        "CUSTOMER_ID": UpstreamColumn("agg_customer_orders", "CUSTOMER_ID"),
        "FIRST_ORDER": UpstreamColumn("agg_customer_orders", "FIRST_ORDER"),
        "CUSTOMER_ID1": UpstreamColumn("exp_stg_customers", "CUSTOMER_ID"),
        "FIRST_NAME": UpstreamColumn("exp_stg_customers", "FIRST_NAME"),
    }
    sql = generate_joiner(joiner, port_sources)
    assert "left join" in sql
    # detail (exp_stg_customers) must be the preserved/FROM side, master is the joined side
    from_clause = sql.split("left join")[0]
    assert "from exp_stg_customers" in from_clause
    assert "left join agg_customer_orders" in sql
    assert "agg_customer_orders.CUSTOMER_ID = exp_stg_customers.CUSTOMER_ID" in sql


def test_generate_projection_rejects_more_than_one_upstream_source():
    exp = Transformation(
        name="EXP_bad",
        type="Expression",
        ports=[Port(name="A", datatype="integer", porttype="INPUT/OUTPUT")],
    )
    port_sources = {
        "A": UpstreamColumn("one_upstream", "A"),
        "B": UpstreamColumn("another_upstream", "B"),
    }
    with pytest.raises(ValueError, match="single upstream"):
        generate_projection(exp, port_sources)


def test_generate_joiner_rejects_more_than_two_upstream_sources():
    joiner = Transformation(
        name="JNR_bad",
        type="Joiner",
        ports=[Port(name="A", datatype="integer", porttype="INPUT/OUTPUT")],
        table_attributes={
            "Join Condition": "A = A",
            "Join Type": "Normal Join",
            "Master Ports": "A",
        },
    )
    port_sources = {
        "A": UpstreamColumn("first", "A"),
        "B": UpstreamColumn("second", "B"),
        "C": UpstreamColumn("third", "C"),
    }
    with pytest.raises(ValueError, match="exactly two upstream sources"):
        generate_joiner(joiner, port_sources)
