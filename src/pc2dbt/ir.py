"""Intermediate representation for a PowerCenter mapping.

parser.py builds these dataclasses from the mapping XML. Nothing outside
parser.py should ever touch the XML directly - everything else works from
this IR.
"""

from dataclasses import dataclass, field


@dataclass
class Field:
    """A column on a physical source or target table."""

    name: str
    datatype: str


@dataclass
class Source:
    """A SOURCE definition - a physical table a mapping reads from."""

    name: str
    fields: list[Field]


@dataclass
class Target:
    """A TARGET definition - the physical table a mapping writes to."""

    name: str
    fields: list[Field]


@dataclass
class Port:
    """A single field on a transformation.

    porttype is one of "INPUT", "OUTPUT", "INPUT/OUTPUT" (PowerCenter's
    TRANSFORMFIELD PORTTYPE attribute). expression/expression_type are only
    set on OUTPUT ports that compute a value (EXPRESSIONTYPE "GENERAL") or
    on ports that participate in a GROUP BY (EXPRESSIONTYPE "GROUPBY").
    """

    name: str
    datatype: str
    porttype: str
    expression: str | None = None
    expression_type: str | None = None


@dataclass
class Transformation:
    """A named transformation definition (Source Qualifier, Expression,
    Joiner, Aggregator, ...) and its ports.

    table_attributes holds transformation-level settings that aren't ports,
    e.g. a Joiner's "Join Condition", "Join Type", "Master Ports".
    """

    name: str
    type: str
    ports: list[Port]
    table_attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class Instance:
    """A node in the mapping's data flow graph.

    Each INSTANCE points at a Source, Target, or Transformation definition
    by name. Instances (not the definitions they point at) are what
    CONNECTORs link together.
    """

    name: str
    type: str
    transformation_name: str
    transformation_type: str


@dataclass
class Connector:
    """A single field-to-field edge between two instances."""

    from_instance: str
    from_field: str
    to_instance: str
    to_field: str


@dataclass
class Mapping:
    """A full PowerCenter mapping: sources, one target, transformations,
    and the instance graph connecting them."""

    name: str
    sources: dict[str, Source]
    target: Target
    transformations: dict[str, Transformation]
    instances: list[Instance]
    connectors: list[Connector]
