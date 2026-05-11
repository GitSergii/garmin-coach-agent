---
name: fitness-analysis
description: Analyze recent fitness trends, load, and fatigue indicators. Use when the user asks about progress, trend direction, intensity balance, or recovery risk.
metadata:
  adk_additional_tools:
    - analyze_fitness
---

## When to use

Use this skill when the user asks:
- "Am I improving?"
- "How is my load trend?"
- "Am I overtraining?"
- "How do intensity and recovery look?"

## Steps

1. Call `analyze_fitness` first.
2. Interpret returned trend/load/fatigue metrics deterministically.
3. Report:
   - trend direction (improving/stable/declining)
   - likely drivers
   - confidence level from data sufficiency
4. Give 1-3 actionable next steps tied to the evidence.

## Safety and boundaries

- Do not give medical diagnosis.
- Do not claim certainty when data windows are short.
- Keep conclusions tied to available metrics only.

## Edge cases

- If signal quality is low, label confidence as low and recommend more data collection.
- If metrics conflict (for example performance up but fatigue high), present both and choose conservative advice.

See `references/trend-interpretation.md` for interpretation rules.
