---
name: coach-context
description: Load recent athlete context before giving coaching advice. Use when users ask how they are doing recently, ask for status, or request guidance based on current training data.
metadata:
  adk_additional_tools:
    - get_context_data
---

## When to use

Use this skill when the user asks:
- "How am I doing?"
- "Summarize my recent week"
- "Any advice based on my current data?"
- any coaching question that depends on latest context

## Steps

1. Call `get_context_data` before giving recommendations.
2. Read key context in this order:
   - data freshness
   - recent activities and load
   - sleep/recovery signals
   - active goals
3. If data looks sparse or stale, state that explicitly before advice.
4. Give concise, data-grounded guidance and avoid speculation.

## Response style

- Keep response short and practical for chat.
- Separate **facts** from **recommendations**.
- If confidence is low, say why.

## Edge cases

- If tool returns missing/empty fields, do not invent values.
- If activity data exists but recovery data is missing, mark recovery uncertainty.
- If goals are missing, give neutral guidance and suggest setting goals.

See `references/context-policy.md` for context freshness and confidence rules.
