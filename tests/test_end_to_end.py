"""Runs the generated model against the jaffle_shop_duckdb seed data and
diffs it against that project's own `customers` table (already built by
running `dbt seed && dbt run` there - see README for setup).
"""

import re

import duckdb
import pytest

from pc2dbt.emitter import emit_model
from pc2dbt.parser import parse_mapping

REFERENCE_REPO = "/Users/dsofjins/mines/jaffle_shop_duckdb"
REFERENCE_DB = f"{REFERENCE_REPO}/jaffle_shop.duckdb"
SEEDS_DIR = f"{REFERENCE_REPO}/seeds"


def _strip_source_macro(sql: str) -> str:
    """{{ source('group', 'table') }} -> table, so plain DuckDB can run it."""
    return re.sub(r"\{\{\s*source\('[^']+',\s*'([^']+)'\)\s*\}\}", r"\1", sql)


@pytest.fixture(scope="module")
def reference_rows():
    con = duckdb.connect(REFERENCE_DB, read_only=True)
    try:
        yield con.execute("select * from customers order by customer_id").fetchall()
    finally:
        con.close()


@pytest.fixture(scope="module")
def generated_rows():
    mapping = parse_mapping("fixtures/m_customers.xml")
    sql = _strip_source_macro(emit_model(mapping))

    con = duckdb.connect(":memory:")
    for table in ("raw_customers", "raw_orders", "raw_payments"):
        con.execute(f"create table {table} as select * from read_csv_auto('{SEEDS_DIR}/{table}.csv')")

    return con.execute(f"{sql} order by CUSTOMER_ID").fetchall()


def test_row_count_matches_reference(reference_rows, generated_rows):
    assert len(generated_rows) == len(reference_rows)


def test_generated_customers_matches_reference_row_for_row(reference_rows, generated_rows):
    assert generated_rows == reference_rows
