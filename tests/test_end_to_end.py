"""Runs the generated model against jaffle_shop's own seed data and SQL,
and diffs the result row-for-row against jaffle_shop's own customers model.

Fully self-contained: no external clone, no dbt install, no network access.
`tests/fixtures/jaffle_shop_reference/` vendors the small slice of
dbt-labs/jaffle_shop_duckdb (Apache 2.0, see NOTICE.md there) needed to
build that comparison - three seed CSVs and four small SQL model files.
"""

import re

import duckdb
import pytest

from pc2dbt.emitter import emit_model
from pc2dbt.parser import parse_mapping

FIXTURE = "fixtures/m_customers.xml"
REFERENCE_DIR = "tests/fixtures/jaffle_shop_reference"


def _strip_source_macro(sql: str) -> str:
    """{{ source('group', 'table') }} -> table, so plain DuckDB can run it."""
    return re.sub(r"\{\{\s*source\('[^']+',\s*'([^']+)'\)\s*\}\}", r"\1", sql)


def _strip_jinja(sql: str) -> str:
    """Strip a dbt model down to plain SQL DuckDB can run directly:
    drop {# ... #} comment blocks, and turn {{ ref('x') }} into plain x."""
    sql = re.sub(r"\{#.*?#\}", "", sql, flags=re.DOTALL)
    return re.sub(r"\{\{\s*ref\('([^']+)'\)\s*\}\}", r"\1", sql)


def _read_reference_model(name: str) -> str:
    with open(f"{REFERENCE_DIR}/models/{name}.sql") as f:
        return _strip_jinja(f.read())


@pytest.fixture(scope="module")
def duckdb_con():
    con = duckdb.connect(":memory:")
    for table in ("raw_customers", "raw_orders", "raw_payments"):
        con.execute(f"create table {table} as select * from read_csv_auto('{REFERENCE_DIR}/seeds/{table}.csv')")
    yield con
    con.close()


@pytest.fixture(scope="module")
def reference_rows(duckdb_con):
    # Build jaffle_shop's own staging models, then run its own customers model.
    for staging_model in ("stg_customers", "stg_orders", "stg_payments"):
        sql = _read_reference_model(staging_model)
        duckdb_con.execute(f"create view {staging_model} as {sql}")

    sql = _read_reference_model("customers")
    return duckdb_con.execute(f"{sql} order by customer_id").fetchall()


@pytest.fixture(scope="module")
def generated_rows(duckdb_con):
    mapping = parse_mapping(FIXTURE)
    sql = _strip_source_macro(emit_model(mapping))
    return duckdb_con.execute(f"{sql} order by CUSTOMER_ID").fetchall()


def test_row_count_matches_reference(reference_rows, generated_rows):
    assert len(generated_rows) == len(reference_rows)


def test_generated_customers_matches_reference_row_for_row(reference_rows, generated_rows):
    assert generated_rows == reference_rows
