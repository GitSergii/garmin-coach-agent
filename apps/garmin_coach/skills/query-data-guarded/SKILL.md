---
name: query-data-guarded
description: Answer factual data questions with guarded NL2SQL. Use when the user asks for concrete values or comparisons that require querying stored Garmin data.
metadata:
  adk_additional_tools:
    - query_data
---

## When to use

Use this skill only for factual retrieval such as:
- totals, averages, counts, trends over a period
- "how many / what was my / compare last week vs this week"

Prefer non-SQL tools first when they already answer the question.

## Steps

1. Use the registered `query_data` tool to retrieve specific data values from the database.
2. Keep request scoped to the user question; avoid broad exploratory queries.
3. Present results clearly with units and timeframe.
4. If query result is empty, say that explicitly and suggest a narrower range.

## Safety rules

- Never attempt to bypass guardrails.
- Treat tool errors as policy/system constraints, not user mistakes.
- If NL2SQL is disabled, explain and fall back to other available tools.

## Edge cases

- If data is missing for a period, state "no records found" rather than guessing.
- If results are truncated/limited, mention that.

See `references/nl2sql-safety-policy.md` for mandatory constraints.
