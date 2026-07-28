"""Walks the mapping's DAG and assembles the final dbt SQL model text."""

from pc2dbt.ir import Mapping


def emit_model(mapping: Mapping) -> str:
    raise NotImplementedError
