# Agent log

Notes on where the coding agent (me, working through this build) got
something wrong, and how it was caught. Filled in as the build progresses.

## 1. Clever one-liner in the Joiner select-list, against CLAUDE.md's own rule

First draft of `generate_joiner`'s select-list construction built each
column with `f"{alias}.{_passthrough_expression(port.name, column)}"`,
relying on `_passthrough_expression` always returning either `"port_name"`
or `"column as port_name"`, so that prefixing `"alias."` via plain string
concatenation happened to produce correct SQL (`"alias.column as
port_name"`) as a side effect of the *literal text* of the first return
case rather than any qualification logic. It worked and passed the tests
- CLAUDE.md's own hard rule ("no clever one-liners... if a simpler
construct exists, use it") is what caught it on re-read, not a test
failure. Rewrote as a plain `if column == port.name: ... else: ...` loop.
Lesson: a passing test doesn't catch "this only works because of an
implementation detail of a helper function" - that needs a second read
against the stated style rules, not just green tests.

## 2. A test assertion that was wrong, not the implementation

`test_generate_projection_expression_with_rename_and_computation` asserted
`sql.count("\n    ID") == 0` to check that a pure-INPUT port isn't
projected standalone. It failed - but the real bug was the assertion:
`"ID as PAYMENT_ID"` legitimately starts with `"ID"`, so the substring
check was always going to find a match regardless of correctness. Caught
by reading the actual generated SQL in the failure output before touching
the generator - the SQL was right, the test's string-matching logic
wasn't. Rewrote to split the SQL into stripped lines and check none of
them equals exactly `"ID"`.

## 3. Assumed one arbitrary CTE ordering was the only valid one

`test_emits_a_cte_per_source_and_per_transformation_in_dependency_order`
originally asserted the emitted CTEs would appear in the exact order
`list(mapping.sources) + list(mapping.transformations)` (all sources
grouped first, then all transformations in XML document order). It
failed against a topological order that interleaves
`raw_customers, SQ_raw_customers, raw_orders, SQ_raw_orders, ...` - which
is equally valid, just a different (also correct) topological sort of the
same DAG. Caught by printing the actual emitted CTE order and checking it
against the mapping's actual dependency edges rather than assuming the
test's expected order was the spec. Rewrote the test to check the only
real invariant - every CTE appears after everything that feeds it - via
the mapping's own connectors, instead of hard-coding one specific valid
ordering.

## 4. Reimplemented what the standard library already does

First draft of `graph.py` hand-rolled a recursive depth-first-search
topological sort, including its own `visited`/`in_progress` bookkeeping to
detect cycles. Python's standard library has had exactly this - a
topological sorter with built-in cycle detection - since 3.9 (`graphlib.
TopologicalSorter`), and this project already required 3.11+. Caught in a
dedicated multi-angle review pass (see below) that specifically checked
the diff for reuse opportunities, not by anything failing. Replaced ~20
lines of hand-rolled recursion with a 2-line call to the stdlib class.

## 5. The same "alias.column, renamed if needed" logic written three times

`generate_joiner`'s select-list, `generators._passthrough_expression`, and
`emitter._build_final_select` each independently re-derived the same
"qualify with an alias if there is one, append `as new_name` if the column
was renamed" logic, with slightly different code each time. Also caught by
the review pass, not a failure - all three call sites currently produced
correct output, so nothing was actually broken, just harder to change
consistently later (fix the rule in one place, forget the other two).
Consolidated into one `column_reference()` helper used everywhere.

## 6. Two places that silently trusted an assumption instead of checking it

`single_upstream_alias` (used by Source Qualifier/Expression/Aggregator
generation) just took the first upstream alias it found via
`next(iter(port_sources.values()))`, without checking whether every port
actually came from the *same* upstream - if a differently-shaped mapping
ever fed one of these transformation types from two different upstream
CTEs, this would have silently picked one of them and produced a `FROM`
that quietly dropped/misattributed data, no error at all. Similarly,
`generate_joiner`'s detail-alias lookup (`next(alias for alias in
all_aliases if alias != master_alias)`) would raise a bare, confusing
`StopIteration` - not a domain error - if there weren't exactly two
upstream aliases. Both were flagged by a review pass looking specifically
for "special case papering over a general mechanism instead of the
mechanism enforcing its own assumption." Fixed by making both functions
count the actual number of distinct upstream aliases and raise a clear
`ValueError` naming what they found when it isn't what they expect,
instead of assuming the fixture's shape always holds.

## 7. Bare (alias, column) tuples whose meaning lived only in a comment

`port_sources` values were plain 2-tuples - `port_sources[name][0]` was
"the alias," `[1]` was "the column," but the only place that said so was a
sentence in a module docstring, not anything visible at the call sites
themselves (`alias, column = port_sources[name]` reads fine only if you
already remember the order). Not caught by any test or automated review -
caught by being asked directly "are you sure this is as simple and
readable as it can be, for any Python developer, not just an LLM?" and
rereading the file specifically hunting for exactly this kind of thing.
Replaced with `UpstreamColumn(alias, column)`, a `NamedTuple`, so every
read is self-describing (`.alias`, `.column`) while still unpacking like an
ordinary tuple everywhere it already did. Same follow-up also caught one
leftover ternary in `column_reference` that was inconsistent with this
project's otherwise-consistent "no clever one-liners" style.

## 8. Required a live external clone for one test, when it didn't need to

The original end-to-end test asked whoever ran the suite to separately
`git clone` jaffle_shop_duckdb, install `dbt-duckdb`, and run
`dbt seed && dbt run` there first - a real setup tax for a single test,
and a design choice I didn't reconsider on my own; it took being asked
directly "doesn't it seem weird to clone the other project for one test?"
to actually question it. On reflection the live clone bought nothing the
comparison actually needed: jaffle_shop's reference answer only depends on
~450 lines of its own seed CSVs and SQL model files (Apache 2.0 licensed),
not on `dbt` itself - dbt's job is just rendering Jinja and running SQL,
both of which the test can do directly against DuckDB with a couple of
regex substitutions (the same trick already used for our own generated
SQL's `{{ source(...) }}` calls). Vendored that small slice into
`tests/fixtures/jaffle_shop_reference/` instead, and rewrote the test to
build jaffle_shop's staging models and run its `customers.sql` itself, in
the same in-memory DuckDB session as our own generated SQL. Net effect:
`pytest -q` now runs the full suite, including this comparison, with zero
external clones, zero extra installs, and no network access - and it still
passed row-for-row (100/100) after the rewrite.

## End-to-end verification: passed clean on the first run

Contrary to the build plan's expectation of "1-2 mismatches on first run"
(e.g. NULL handling for order-less customers), the generated model
matched the reference `customers` table row-for-row (100/100) on the
first attempt, including NULLs for the 25 or so customers with no orders.
Worth recording as a case where nothing needed fixing - verified by
manually printing both result sets and a mismatch count, not just trusting
the green pytest run.
