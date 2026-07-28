from pc2dbt.parser import parse_mapping

FIXTURE = "fixtures/m_customers.xml"


def test_parses_mapping_name_and_target():
    mapping = parse_mapping(FIXTURE)
    assert mapping.name == "m_customers"
    assert mapping.target.name == "customers"


def test_parses_sources():
    mapping = parse_mapping(FIXTURE)
    assert set(mapping.sources) == {"raw_customers", "raw_orders", "raw_payments"}
    customers_fields = [f.name for f in mapping.sources["raw_customers"].fields]
    assert customers_fields == ["ID", "FIRST_NAME", "LAST_NAME"]


def test_parses_target_fields_in_order():
    mapping = parse_mapping(FIXTURE)
    field_names = [f.name for f in mapping.target.fields]
    assert field_names == [
        "CUSTOMER_ID",
        "FIRST_NAME",
        "LAST_NAME",
        "FIRST_ORDER",
        "MOST_RECENT_ORDER",
        "NUMBER_OF_ORDERS",
        "CUSTOMER_LIFETIME_VALUE",
    ]


def test_parses_all_transformations_with_correct_types():
    mapping = parse_mapping(FIXTURE)
    expected_types = {
        "SQ_raw_customers": "Source Qualifier",
        "SQ_raw_orders": "Source Qualifier",
        "SQ_raw_payments": "Source Qualifier",
        "EXP_stg_customers": "Expression",
        "EXP_stg_orders": "Expression",
        "EXP_stg_payments": "Expression",
        "JNR_payments_orders": "Joiner",
        "AGG_customer_orders": "Aggregator",
        "AGG_customer_payments": "Aggregator",
        "JNR_customers_orders": "Joiner",
        "JNR_customers_payments": "Joiner",
        "EXP_final": "Expression",
    }
    assert set(mapping.transformations) == set(expected_types)
    for name, expected_type in expected_types.items():
        assert mapping.transformations[name].type == expected_type


def test_transformation_ports_carry_expression_info():
    mapping = parse_mapping(FIXTURE)
    exp_stg_customers = mapping.transformations["EXP_stg_customers"]
    ports_by_name = {p.name: p for p in exp_stg_customers.ports}

    assert ports_by_name["ID"].porttype == "INPUT"
    assert ports_by_name["FIRST_NAME"].porttype == "INPUT/OUTPUT"
    assert ports_by_name["CUSTOMER_ID"].porttype == "OUTPUT"
    assert ports_by_name["CUSTOMER_ID"].expression == "ID"
    assert ports_by_name["CUSTOMER_ID"].expression_type == "GENERAL"


def test_aggregator_groupby_ports():
    mapping = parse_mapping(FIXTURE)
    agg = mapping.transformations["AGG_customer_orders"]
    ports_by_name = {p.name: p for p in agg.ports}
    assert ports_by_name["CUSTOMER_ID"].expression_type == "GROUPBY"
    assert ports_by_name["FIRST_ORDER"].expression == "MIN(ORDER_DATE)"


def test_joiner_table_attributes():
    mapping = parse_mapping(FIXTURE)
    joiner = mapping.transformations["JNR_payments_orders"]
    assert joiner.table_attributes["Join Condition"] == "ORDER_ID = ORDER_ID1"
    assert joiner.table_attributes["Join Type"] == "Normal Join"
    assert joiner.table_attributes["Master Ports"] == "ORDER_ID,CUSTOMER_ID"


def test_instance_and_connector_counts():
    mapping = parse_mapping(FIXTURE)
    assert len(mapping.instances) == 16
    assert len(mapping.connectors) == 60


def test_a_specific_connector():
    mapping = parse_mapping(FIXTURE)
    match = [
        c
        for c in mapping.connectors
        if c.from_instance == "raw_customers" and c.from_field == "FIRST_NAME"
    ]
    assert len(match) == 1
    assert match[0].to_instance == "SQ_raw_customers"
    assert match[0].to_field == "FIRST_NAME"
