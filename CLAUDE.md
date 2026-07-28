# pc2dbt — agent guardrails

Converts an Informatica PowerCenter mapping XML (powrmart format) into an
equivalent dbt SQL model. Input fixture: `fixtures/m_customers.xml` (mirrors
the dbt jaffle_shop `customers` model, but the converter must not assume it).

## Architecture (do not deviate without asking)

- Pipeline: XML -> intermediate representation (IR, dataclasses) -> SQL emitter.
- `parser.py` reads XML into IR. Nothing downstream touches XML.
- One generated CTE per PowerCenter transformation, chained in topological
  order; final `SELECT` at the end. One model file per mapping.
- Port rules: OUTPUT ports -> select expressions with aliases; INPUT/OUTPUT ->
  passthrough columns; pure INPUT -> consumed, not emitted.
- Joiners: `"Normal Join"` -> INNER JOIN; `"Master Outer Join"` -> detail
  LEFT JOIN master. Master side = ports listed in the `"Master Ports"`
  TABLEATTRIBUTE.
- Aggregators: `EXPRESSIONTYPE="GROUPBY"` ports -> GROUP BY + select list.

## Hard rules

- NEVER hard-code names from the fixture (no "customers", "jaffle",
  "ORDER_ID" literals in converter logic). The converter must work on any
  structurally similar mapping.
- Unknown transformation types: raise a clear error naming the type.
  Do not guess.
- Tests first: each generator gets a failing test from a small XML
  fragment before implementation. Run `pytest` before declaring any task done.
- Keep Python beginner-friendly: dataclasses, plain functions, stdlib
  `xml.etree`. No metaprogramming, no clever one-liners. If a simpler
  construct exists, use it.
- Small diffs. One bounded task per request. Stop and summarize after each.

## Verification target

Generated model, run via jaffle_shop_duckdb seeds, must reproduce the
reference `customers` table. Do not "fix" mismatches by editing expected
outputs — investigate the converter.
