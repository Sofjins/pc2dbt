"""XML -> IR. Reads a PowerCenter mapping XML export and builds a Mapping."""

import xml.etree.ElementTree as ET

from pc2dbt.ir import Connector, Field, Instance, Mapping, Port, Source, Target, Transformation


def parse_mapping(xml_path: str) -> Mapping:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    folder = root.find("REPOSITORY/FOLDER")

    sources = {s.name: s for s in (_parse_source(el) for el in folder.findall("SOURCE"))}
    targets = {t.name: t for t in (_parse_target(el) for el in folder.findall("TARGET"))}

    mapping_el = folder.find("MAPPING")
    transformations = {
        t.name: t
        for t in (_parse_transformation(el) for el in mapping_el.findall("TRANSFORMATION"))
    }
    instances = [_parse_instance(el) for el in mapping_el.findall("INSTANCE")]
    connectors = [_parse_connector(el) for el in mapping_el.findall("CONNECTOR")]

    # This fixture (and the converter's scope) assumes a single target per mapping.
    target = next(iter(targets.values()))

    return Mapping(
        name=mapping_el.get("NAME"),
        source_group=folder.get("NAME").lower(),
        sources=sources,
        target=target,
        transformations=transformations,
        instances=instances,
        connectors=connectors,
    )


def _parse_source(el: ET.Element) -> Source:
    fields = [_parse_field(f, "SOURCEFIELD") for f in el.findall("SOURCEFIELD")]
    return Source(name=el.get("NAME"), fields=fields)


def _parse_target(el: ET.Element) -> Target:
    fields = [_parse_field(f, "TARGETFIELD") for f in el.findall("TARGETFIELD")]
    return Target(name=el.get("NAME"), fields=fields)


def _parse_field(el: ET.Element, tag: str) -> Field:
    return Field(name=el.get("NAME"), datatype=el.get("DATATYPE"))


def _parse_transformation(el: ET.Element) -> Transformation:
    ports = [_parse_port(f) for f in el.findall("TRANSFORMFIELD")]
    table_attributes = {
        a.get("NAME"): a.get("VALUE") for a in el.findall("TABLEATTRIBUTE")
    }
    return Transformation(
        name=el.get("NAME"),
        type=el.get("TYPE"),
        ports=ports,
        table_attributes=table_attributes,
    )


def _parse_port(el: ET.Element) -> Port:
    return Port(
        name=el.get("NAME"),
        datatype=el.get("DATATYPE"),
        porttype=el.get("PORTTYPE"),
        expression=el.get("EXPRESSION"),
        expression_type=el.get("EXPRESSIONTYPE"),
    )


def _parse_instance(el: ET.Element) -> Instance:
    return Instance(
        name=el.get("NAME"),
        type=el.get("TYPE"),
        transformation_name=el.get("TRANSFORMATION_NAME"),
        transformation_type=el.get("TRANSFORMATION_TYPE"),
    )


def _parse_connector(el: ET.Element) -> Connector:
    return Connector(
        from_instance=el.get("FROMINSTANCE"),
        from_field=el.get("FROMFIELD"),
        to_instance=el.get("TOINSTANCE"),
        to_field=el.get("TOFIELD"),
    )
