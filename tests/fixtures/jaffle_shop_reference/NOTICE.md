# Vendored reference files

The `seeds/` and `models/` files in this folder are copied unmodified from
[dbt-labs/jaffle_shop_duckdb](https://github.com/dbt-labs/jaffle_shop_duckdb),
licensed under Apache 2.0 (see `LICENSE`).

They exist here so `tests/test_end_to_end.py` can compare pc2dbt's generated
SQL against jaffle_shop's own reference `customers` model without requiring
a live clone of that project or a `dbt` install - just these ~450 lines of
CSV/SQL, run directly against an in-memory DuckDB database.
