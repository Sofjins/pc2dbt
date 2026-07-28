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

## End-to-end verification: passed clean on the first run

Contrary to the build plan's expectation of "1-2 mismatches on first run"
(e.g. NULL handling for order-less customers), the generated model
matched the reference `customers` table row-for-row (100/100) on the
first attempt, including NULLs for the 25 or so customers with no orders.
Worth recording as a case where nothing needed fixing - verified by
manually printing both result sets and a mismatch count, not just trusting
the green pytest run.
