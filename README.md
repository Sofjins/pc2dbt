# pc2dbt — Informatica PowerCenter → dbt converter

Converts a PowerCenter mapping export (powrmart XML) into an equivalent dbt
SQL model: one CTE per PowerCenter transformation, chained in dependency
order, ending in a final `SELECT` shaped to the mapping's target table.

Built against the sample mapping in `fixtures/m_customers.xml`, which mirrors
(but does not literally reproduce) the dbt [jaffle_shop](https://github.com/dbt-labs/jaffle_shop_duckdb)
`customers` model. The converter itself never references jaffle_shop-specific
names — it only knows about PowerCenter concepts (sources, targets,
transformations, ports, connectors).

## How to run it

```bash
python3 -m venv venv && source venv/bin/activate
pip install -e .          # installs pc2dbt itself (pure stdlib, no deps)
pip install pytest duckdb # dev/test dependencies only

python -m pc2dbt fixtures/m_customers.xml -o out
cat out/customers.sql
```

Run the tests:

```bash
pytest -q
```

`tests/test_end_to_end.py` additionally verifies the generated SQL against
the real jaffle_shop_duckdb project. That test expects a sibling checkout at
`../jaffle_shop_duckdb` with `dbt seed && dbt run` already executed there
(so `jaffle_shop.duckdb` exists):

```bash
cd ..
git clone https://github.com/dbt-labs/jaffle_shop_duckdb
cd jaffle_shop_duckdb
python3 -m venv venv && source venv/bin/activate
pip install dbt-duckdb
DBT_PROFILES_DIR=. dbt seed && DBT_PROFILES_DIR=. dbt run
```

If that sibling repo isn't present, `test_end_to_end.py` will fail on a file-
not-found error rather than silently skipping — that's intentional, so a
missing reference project is never mistaken for a passing test.

## How the mapping was read

`fixtures/m_customers.xml` describes: three sources (`raw_customers`,
`raw_orders`, `raw_payments`) → per-source passthrough/rename Expressions →
a Joiner attaching `customer_id` to payments via orders → two Aggregators
(order stats, payment totals, both grouped by `customer_id`) → two Joiners
that fold those aggregates onto the full customer list, preserving
customers with no orders/payments (`Master Outer Join`) → a final Expression
renaming into the target's column names → the `customers` target.

## Architecture

- `parser.py`: XML → IR (dataclasses in `ir.py`: `Mapping`, `Source`,
  `Target`, `Transformation`, `Port`, `Instance`, `Connector`). Nothing else
  touches the XML.
- `graph.py`: topological sort over the instance graph (a depth-first
  post-order over `CONNECTOR` edges), with cycle detection.
- `generators.py`: one function per PowerCenter transformation type
  (`generate_source_import`, `generate_projection` for Source Qualifier and
  Expression, `generate_aggregator`, `generate_joiner`), each a pure function
  from a `Transformation` + a `port -> (upstream_alias, upstream_column)`
  map to a SQL fragment.
- `emitter.py`: walks the topological order, builds that port-source map
  from the mapping's connectors, dispatches to the right generator, and
  assembles the CTEs plus a final `SELECT` matched to the target's column
  list and order.
- `cli.py` / `__main__.py`: `python -m pc2dbt <xml> -o <dir>`.

Zero runtime dependencies — `xml.etree` and `dataclasses` only. `pytest` and
`duckdb` are dev/test-only.

## Port and join rules implemented

- `OUTPUT` port with an `EXPRESSION` → a computed select column, aliased to
  the port name. Any local port names referenced in the expression text are
  substituted with whatever upstream column actually feeds them (so a
  renamed input, e.g. `AMOUNT_CENTS` fed from an upstream `AMOUNT` column,
  resolves correctly inside `AMOUNT_CENTS / 100`).
- `INPUT/OUTPUT` port → passthrough column (aliased only if the upstream
  column name differs from the local port name).
- Pure `INPUT` port → consumed by an expression or a join condition, never
  projected on its own.
- Aggregator: ports with `EXPRESSIONTYPE="GROUPBY"` become the `GROUP BY`
  list (and are also selected); other `OUTPUT` ports carry the aggregate
  expression.
- Joiner: `"Join Type"="Normal Join"` → `INNER JOIN`.
  `"Join Type"="Master Outer Join"` → detail side `LEFT JOIN` master side
  (PowerCenter's Master Outer Join keeps every row from the detail table).
  The `"Master Ports"` table attribute says which upstream is master; the
  `"Join Condition"` attribute is translated into an aliased `ON` clause by
  resolving each side's local port name back to its upstream column via the
  connectors.
- Unknown transformation types raise `ValueError` naming the type — the
  converter never guesses at a transformation it doesn't implement.

## What was assumed, and what wasn't handled

- **Single mapping, single target per XML file.** The parser takes the
  first (only) `<MAPPING>` and the first (only) `<TARGET>` in the folder.
  A repository with multiple mappings or a mapping with multiple targets
  isn't handled.
- **Transformation types implemented:** Source Qualifier, Expression,
  Aggregator, Joiner (the four in the fixture). PowerCenter also has
  Filter, Router, Lookup, Update Strategy, Sequence Generator, Sorter, and
  others — none of these are implemented. The converter raises a clear
  `ValueError` rather than silently skipping or guessing at one.
- **Expression translation is textual substitution, not real parsing.**
  `port.expression` (e.g. `"AMOUNT_CENTS / 100"`, `"MIN(ORDER_DATE)"`) is
  treated as already-valid SQL, with local port names swapped for their
  resolved upstream column via word-boundary regex substitution. This
  works for the fixture's arithmetic and aggregate functions, but
  PowerCenter's expression language has many built-in functions
  (`IIF`, `DECODE`, `TO_CHAR`, date arithmetic, etc.) that are **not**
  translated to their SQL/dbt equivalents — anything beyond bare
  arithmetic or a handful of aggregate calls would pass through as
  literal (and likely invalid) SQL text.
- **Each Expression/Aggregator has exactly one upstream transformation.**
  This holds for the fixture. A transformation fed by more than one
  upstream instance is only handled for Joiners (which explicitly have
  two).
- **Source/target column casing is preserved as-is** (uppercase, matching
  the XML) rather than lowercased to match dbt/jaffle_shop style. This is
  a deliberate choice to avoid hardcoding a casing convention that isn't in
  the XML; DuckDB (and most warehouses) treat unquoted identifiers
  case-insensitively, so this doesn't affect correctness, only cosmetics.
- **`source_group` for `{{ source(...) }}`** is taken from the XML's
  `<FOLDER NAME="...">`, lowercased. There's no `sources.yml` generation —
  the README's manual test setup resolves `source()` calls by stripping the
  macro down to the bare table name and querying seed tables directly.
- **No Filter transformation in the fixture**, so the generated model never
  excludes rows by status — unlike the real jaffle_shop project's history
  (which at points filtered out `'error'` payments). This isn't a converter
  gap; it's a faithful conversion of a mapping that genuinely has no filter
  step. If a Filter transformation appeared in a mapping, the converter
  would currently raise `ValueError: Unsupported transformation type: 'Filter'`
  rather than fabricate a `WHERE` clause.
- **No generated tests/docs/schema.yml.** Only the SQL model is produced.

## Where the converter is most likely to produce wrong output

- **Any transformation type outside {Source Qualifier, Expression,
  Aggregator, Joiner}** — it will hard-fail rather than emit anything, which
  is the intended behavior, but it means broader mappings (with Lookups,
  Routers, Filters, ...) aren't convertible yet.
- **Non-trivial PowerCenter expressions** — anything using PowerCenter
  built-in functions that don't already look like valid SQL (`IIF`,
  `DECODE`, PowerCenter date functions, string functions with different
  names than their SQL equivalents) will be emitted verbatim and likely
  fail to run, since there's no real expression parser/translator, just
  textual port-name substitution.
- **A transformation fed by more than two upstream instances**, or an
  Expression/Aggregator fed by more than one upstream instance — the
  "single upstream alias" assumption in `generate_projection` /
  `generate_aggregator` would silently pick an arbitrary one of the
  upstream aliases (via `next(iter(...))`) rather than erroring, which
  could produce a plausible-looking but wrong `FROM` clause.
- **Multiple mappings or multiple targets in one XML file** — only the
  first of each is used; nothing warns that others were ignored.
- **Reusable transformations** (`REUSABLE="YES"`, shared across mappings)
  aren't specifically handled; the converter assumes a 1:1 mapping between
  instance name and transformation definition, which held for this fixture
  but isn't guaranteed by the format in general.

## Where a coding agent got something wrong, and how it was caught

See `AGENT_LOG.md` for the full detail. Short version: a clever
string-concatenation shortcut in the Joiner generator that only worked
because of an implementation detail in a helper function (caught on
re-reading against this project's own "no clever one-liners" rule, not by
a failing test); a test assertion that was itself wrong rather than the
code it was testing (caught by reading the actual generated SQL in the
failure output before "fixing" anything); and a test that baked in one
arbitrary — but not the only — valid topological ordering of the CTEs
(caught by checking the emitted order against the mapping's actual
dependency edges instead of assuming the test's expectation was the spec).
The end-to-end DuckDB comparison against the real jaffle_shop project passed
row-for-row (100/100) on the first attempt.
