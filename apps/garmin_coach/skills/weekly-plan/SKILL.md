---
name: weekly-plan
description: Build a safe and practical weekly running plan from goal and recent load. Use when users ask for a next-week plan, training structure, or schedule recommendations.
metadata:
  adk_additional_tools:
    - weekly_plan
---

## When to use

Use this skill for:
- weekly training plan requests
- race prep week structure
- "what should I do next week?" questions

## Inputs and assumptions

Call `weekly_plan` with:
- `goal_description`
- `norwegian_method` (default true unless user asks otherwise)
- `max_hours_per_week` aligned to user constraints

If inputs are ambiguous, state assumptions explicitly.

## Planning rules

1. Keep progression conservative relative to recent load.
2. Include recovery and easy days.
3. Avoid abrupt spikes in intensity and volume.
4. Favor consistency over aggressive overload.
5. Keep the plan adjustable based on feedback/recovery.

## Output format

Provide:
- weekly objective
- day-by-day structure
- key workout intent
- load/risk notes
- adjustment guidance if fatigue rises

Use `assets/weekly-plan-template.md` when useful.
See `references/progression-rules.md` and `references/norwegian-method.md`.
