# pc2dbt — Informatica PowerCenter → dbt converter

Converts an Informatica PowerCenter mapping (exported as XML, the "powrmart"
format) into an equivalent dbt SQL model. Each PowerCenter transformation
becomes one CTE. The CTEs are ordered so each one only refers to CTEs
already defined above it. The whole thing ends in one final `SELECT`
shaped to match the mapping's target table.

Built and tested against the sample mapping in `fixtures/m_customers.xml`.
That mapping is similar to — but not the same as — the public dbt
[jaffle_shop](https://github.com/dbt-labs/jaffle_shop_duckdb) demo
project's `customers` model. The converter itself doesn't know anything
about jaffle_shop specifically: it only understands generic PowerCenter
concepts (sources, targets, transformations, ports, connectors), so it
should work on any similarly-shaped mapping, not just this one.

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

### One test needs a second project checked out first

Most of the tests just check that the generated SQL text looks right. One
test, `tests/test_end_to_end.py`, goes further: it actually runs the
generated SQL against real sample data and checks the result matches a
known-correct answer.

That known-correct answer comes from the public `jaffle_shop_duckdb`
project, which already has its own hand-written `customers` model and its
own sample data — the same sample data this project's fixture is based on.
So before running the full test suite, clone that project as a sibling
folder (next to this one, not inside it) and build it once:

```bash
cd ..
git clone https://github.com/dbt-labs/jaffle_shop_duckdb
cd jaffle_shop_duckdb
python3 -m venv venv && source venv/bin/activate
pip install dbt-duckdb
DBT_PROFILES_DIR=. dbt seed && DBT_PROFILES_DIR=. dbt run
```

`dbt seed` loads jaffle_shop's sample CSVs into a local database file
(`jaffle_shop.duckdb`). `dbt run` then builds their `customers` model into
that same file. Our test reads that file afterward as the "correct"
answer, separately loads the same sample CSVs fresh, runs our own
generated SQL against them, and checks the two results match row for row.

If that sibling project isn't there, `test_end_to_end.py` fails with a
clear file-not-found error instead of quietly skipping. That's deliberate:
a skipped test and a passing test can look the same at a glance, and this
is the single most important check in the whole suite — it should never be
possible to think it ran and passed when it never actually ran.

## How the mapping was read

In plain terms, this mapping works out, for every customer: their first
and most recent order date, how many orders they've placed, and how much
they've paid in total — including customers who have no orders yet.

More precisely, `fixtures/m_customers.xml` describes: three sources
(`raw_customers`, `raw_orders`, `raw_payments`) → per-source
passthrough/rename Expressions → a Joiner attaching `customer_id` to
payments via orders → two Aggregators (order stats, payment totals, both
grouped by `customer_id`) → two Joiners that fold those aggregates onto
the full customer list, keeping customers with no orders/payments
(`Master Outer Join`) → a final Expression renaming columns to match the
target → the `customers` target.

## Architecture

- `parser.py`: turns the XML into plain Python objects (the dataclasses in
  `ir.py`: `Mapping`, `Source`, `Target`, `Transformation`, `Port`,
  `Instance`, `Connector`). This is the only file that ever touches XML —
  everything downstream works from those plain objects instead.
- `graph.py`: figures out a safe order to emit the CTEs in, using Python's
  standard-library `graphlib.TopologicalSorter` over the mapping's
  `CONNECTOR` edges (which instance feeds which). Raises a clear error if
  the connectors ever formed a cycle, which would mean the mapping is
  invalid.
- `generators.py`: one function per PowerCenter transformation type
  (`generate_source_import`, `generate_projection` for Source Qualifier
  and Expression, `generate_aggregator`, `generate_joiner`). Each is a
  plain function: given one `Transformation` plus a map of "where does
  each of its ports get its value from," it returns a SQL fragment. No
  side effects, no XML, no file I/O.
- `emitter.py`: walks the order from `graph.py`, builds that "where does
  each port's value come from" map from the mapping's connectors, calls
  the right generator for each transformation, and assembles the CTEs plus
  a final `SELECT` matched to the target's column list and order.
- `cli.py` / `__main__.py`: the command line entry point —
  `python -m pc2dbt <xml> -o <dir>`.

Zero runtime dependencies — just `xml.etree` and `dataclasses` from the
standard library. `pytest` and `duckdb` are only needed for testing.

## Port and join rules implemented

- An `OUTPUT` port with an `EXPRESSION` becomes a computed select column,
  aliased to the port's name. Any local port names mentioned inside that
  expression are swapped for whatever upstream column actually feeds them
  — so if an input was renamed (e.g. a port called `AMOUNT_CENTS` is
  actually fed by an upstream column called `AMOUNT`), the expression
  `AMOUNT_CENTS / 100` still resolves to the right column.
- An `INPUT/OUTPUT` port becomes a plain passthrough column (only aliased
  if the upstream column's name is different from the port's own name).
- A pure `INPUT` port is never selected on its own — it only exists to be
  used inside an expression or a join condition.
- Aggregator: ports marked `EXPRESSIONTYPE="GROUPBY"` become the
  `GROUP BY` list (and are also selected as plain columns); other `OUTPUT`
  ports carry the aggregate expression (e.g. `SUM(...)`, `COUNT(...)`).
- Joiner: `"Join Type"="Normal Join"` becomes an `INNER JOIN`.
  `"Join Type"="Master Outer Join"` becomes the detail side `LEFT JOIN`
  the master side — this matches PowerCenter's own definition, where a
  Master Outer Join keeps every row from the detail table. The
  `"Master Ports"` attribute says which upstream is the master side; the
  `"Join Condition"` attribute gets translated into a properly-aliased
  `ON` clause by tracing each side's port name back to its real upstream
  column.
- Any transformation type this converter doesn't recognize raises a clear
  `ValueError` naming the type. It never guesses at how to handle
  something it doesn't actually implement.

## What was assumed, and what wasn't handled

- **One mapping, one target, per XML file.** The parser only looks at the
  first `<MAPPING>` and the first `<TARGET>` it finds. A repository with
  several mappings, or a mapping with more than one target, isn't
  supported.
- **Only four transformation types are implemented:** Source Qualifier,
  Expression, Aggregator, Joiner — the ones actually used in the fixture.
  PowerCenter also has Filter, Router, Lookup, Update Strategy, Sequence
  Generator, Sorter, and others, none of which are implemented. Hitting
  one of these raises a clear `ValueError` instead of silently skipping
  it or guessing at what it should do.
- **Expressions are handled by text substitution, not real parsing.** A
  port's expression (e.g. `"AMOUNT_CENTS / 100"`, `"MIN(ORDER_DATE)"`) is
  treated as if it were already valid SQL, with local port names swapped
  for their real upstream column names. That works fine for the fixture's
  plain arithmetic and aggregate functions. It does **not** work for
  PowerCenter's many built-in functions that don't already look like SQL
  (`IIF`, `DECODE`, `TO_CHAR`, date arithmetic, and so on) — those would be
  copied through as-is and would likely fail to run.
- **Each Expression or Aggregator only supports a single upstream
  transformation.** That's true for every one in the fixture. Only the
  Joiner is built to handle more than one upstream (exactly two, by
  design).
- **Column names keep the exact casing from the XML** (usually uppercase)
  instead of being lowercased to match dbt/jaffle_shop style. This is
  deliberate — lowercasing would mean assuming a naming convention that
  isn't actually written anywhere in the XML. Most databases (including
  DuckDB) treat unquoted column names case-insensitively, so this doesn't
  change correctness, only how the SQL looks.
- **The dbt `source()` group name** comes straight from the XML's
  `<FOLDER NAME="...">`, lowercased. This project doesn't generate a
  `sources.yml` file — the manual test setup above works around that by
  stripping the `source()` call down to a plain table name before running
  the SQL directly against DuckDB.
- **The fixture has no Filter transformation**, so the generated model
  never excludes rows by status. This is not a gap in the converter — it's
  a faithful conversion of a mapping that genuinely has no filtering step.
  If a real mapping did include a Filter, this converter would currently
  raise `ValueError: Unsupported transformation type: 'Filter'` rather than
  invent a `WHERE` clause on its own.
- **No tests, docs, or `schema.yml` are generated** — only the SQL model
  itself.

## Where the converter is most likely to produce wrong output

- **Any transformation type other than Source Qualifier, Expression,
  Aggregator, or Joiner** will stop the conversion entirely rather than
  produce anything — which is the intended, safe behavior, but it does
  mean bigger mappings (with Lookups, Routers, Filters, etc.) can't be
  converted yet.
- **PowerCenter expressions that don't already look like valid SQL** —
  anything using PowerCenter-specific functions (`IIF`, `DECODE`, date
  functions, string functions with different names than their SQL
  equivalents) will be copied through unchanged and will likely fail to
  run, since there's no real expression translator — just simple
  find-and-replace on port names.
- **A transformation fed by more upstream sources than it's designed
  for** — Source Qualifier, Expression, and Aggregator only support a
  single upstream; a Joiner only supports exactly two. Both limits are
  actively checked, so a mapping that violates them raises a clear error
  naming what was found, instead of producing quietly-wrong SQL. So this
  fails safely — it just means such a mapping can't be converted at all.
- **More than one mapping or target in a single XML file** — only the
  first of each gets used, with no warning that anything else was
  ignored.
- **Reusable transformations** (`REUSABLE="YES"`, shared across several
  mappings) aren't specifically handled. The converter assumes each
  instance name matches its own transformation definition one-to-one,
  which is true for this fixture but isn't guaranteed by the format in
  general.

## Where a coding agent got something wrong, and how it was caught

Full detail in `AGENT_LOG.md` — seven entries, caught three different ways:

- **By rereading the code against this project's own stated rules, not a
  failing test:** a clever string-concatenation shortcut in the Joiner
  generator that only happened to work because of an implementation
  detail in a helper function; later, one leftover ternary that didn't
  match the project's own "no clever one-liners" style.
- **By a dedicated review pass**, looking at the code from four different
  angles (reuse, simplification, efficiency, "is this the right depth of
  fix"): a topological sort that reimplemented something Python's
  standard library already provides; the same small piece of logic
  ("qualify a column, rename it if needed") written out three separate
  times instead of once; and two places that quietly assumed something
  ("there's only one upstream source here," "there are exactly two
  upstream sources here") instead of checking it and failing clearly if
  it wasn't true.
- **By being asked directly**, "is this really as simple and readable as
  it can be, for any Python developer — not just an LLM?", and rereading
  with that specific question in mind: plain `(alias, column)` tuples
  whose meaning only existed in a comment, not anywhere visible at the
  places that actually used them. Replaced with a small named type so
  every use of it is self-explanatory.

Also worth recording, because nothing was actually wrong: two of my own
test assertions turned out to be the broken part, not the code they were
testing — a substring check that could never have failed correctly, and a
test that assumed one specific (but not the only) valid ordering of the
generated CTEs. Both were caught by reading the real output in the test
failure before touching any code. And the end-to-end comparison against
the real jaffle_shop project matched, row for row (100 out of 100), on the
very first attempt.
