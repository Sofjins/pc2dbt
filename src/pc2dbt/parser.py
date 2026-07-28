"""XML -> IR. Reads a PowerCenter mapping XML export and builds a Mapping."""

import xml.etree.ElementTree as ET

from pc2dbt.ir import Connector, Field, Instance, Mapping, Port, Source, Target, Transformation


def parse_mapping(xml_path: str) -> Mapping:
    raise NotImplementedError
