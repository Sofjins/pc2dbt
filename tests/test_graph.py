from pc2dbt.graph import topological_order
from pc2dbt.ir import Connector, Instance, Mapping
from pc2dbt.parser import parse_mapping


def _instance(name: str) -> Instance:
    return Instance(name=name, type="Expression", transformation_name=name, transformation_type="Expression")


def test_simple_chain_orders_upstream_before_downstream():
    mapping = Mapping(
        name="m_test",
        source_group="test",
        sources={},
        target=None,
        transformations={},
        instances=[_instance("c"), _instance("a"), _instance("b")],
        connectors=[
            Connector(from_instance="a", from_field="x", to_instance="b", to_field="x"),
            Connector(from_instance="b", from_field="x", to_instance="c", to_field="x"),
        ],
    )
    order = topological_order(mapping)
    assert order.index("a") < order.index("b") < order.index("c")


def test_fan_in_orders_both_upstreams_before_the_joiner():
    mapping = Mapping(
        name="m_test",
        source_group="test",
        sources={},
        target=None,
        transformations={},
        instances=[_instance("join"), _instance("left"), _instance("right")],
        connectors=[
            Connector(from_instance="left", from_field="x", to_instance="join", to_field="x1"),
            Connector(from_instance="right", from_field="x", to_instance="join", to_field="x2"),
        ],
    )
    order = topological_order(mapping)
    assert order.index("left") < order.index("join")
    assert order.index("right") < order.index("join")


def test_fixture_mapping_respects_all_dependencies():
    mapping = parse_mapping("fixtures/m_customers.xml")
    order = topological_order(mapping)
    position = {name: i for i, name in enumerate(order)}
    for connector in mapping.connectors:
        assert position[connector.from_instance] < position[connector.to_instance]
