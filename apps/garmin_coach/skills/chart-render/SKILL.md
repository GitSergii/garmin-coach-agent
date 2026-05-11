---
name: chart-render
description: Generate a chart image and send it to the user. Use this skill immediately whenever the user says show, chart, graph, plot, visualize, draw, display, or asks to see any metric visually. Do not use query_data or any other tool first — call render_chart directly.
metadata:
  adk_additional_tools:
    - render_chart
---

## When to use

Use this skill immediately when the user says any of:
- "show", "chart", "graph", "plot", "visualize", "draw", "display"
- "show my runs", "show sleep", "show HR", "show distance"
- any request to *see* data rather than just read it as text

Do NOT call `query_data` or `get_context_data` before calling `render_chart`.
Do NOT pre-check whether data exists — call `render_chart` directly. It handles missing data itself.
Do not generate charts for simple one-line factual answers.

## Steps

1. Map the user's question to the right chart type and metric using the decision guide below.
2. Compose the `chart_request` spec string (`key=value,key=value`).
3. Call `render_chart(chart_request=<spec>)` — this is always the first and only tool call for chart requests.
4. Return a short interpretation: timeframe, 1-2 key insights, and any actionable note.

## Spec string format

`chart_request` is a comma-separated list of `key=value` pairs:

| Key | Values | Default |
|---|---|---|
| `metric` | column name (see below) | – |
| `chart_type` | `trend` \| `bar` \| `weekly` \| `activity_bars` \| `activity` \| `dashboard` | `dashboard` |
| `days` | integer | `14` |
| `weeks` | integer | `8` |
| `title` | any string | auto |

## Metric column names

| User asks about | metric= value |
|---|---|
| Sleep / rest | `sleep_duration_hours` |
| Sleep quality | `sleep_quality_score` |
| Resting heart rate | `resting_heart_rate` |
| Heart rate | `avg_heart_rate` |
| Steps | `steps` |
| Distance / runs | `distance_km` |
| Active minutes | `active_minutes` |
| Stress | `stress_level_avg` |
| Body battery | `body_battery_level` |
| VO2 max | `vo2_max` |
| Calories | `calories_burned` |

## Chart type selection — decision guide

Pick the chart type that best answers the user's actual question. Do not default to `trend` or `dashboard` when a more specific type fits.

| User says | chart_type | metric | days/weeks |
|---|---|---|---|
| "last N days sleep/HR/steps trend" | `trend` | matching column | N |
| "show each day as bars", "daily breakdown" | `bar` | matching column | N |
| "each week", "weekly volume" | `weekly` | `distance_km` or other | weeks |
| "show each run", "individual runs", "per run" | `activity_bars` | `distance_km` | N |
| "last run", "splits", "pace chart" | `activity` | – | – |
| "overview", "dashboard", "all metrics" | `dashboard` | – | – |

Key rule: if the user wants to see **individual items** (each run separately, each day separately), prefer `activity_bars` or `chart_type=bar`. Only use `weekly` when they explicitly ask for week-level aggregation.

## Examples

- "Show my sleep over the last 2 weeks" → `"metric=sleep_duration_hours,days=14"` (auto-bars for sleep)
- "Resting HR trend this month" → `"metric=resting_heart_rate,chart_type=trend,days=30"`
- "Daily distance last 7 days as bars" → `"metric=distance_km,chart_type=bar,days=7"`
- "Show me each run this week" → `"chart_type=activity_bars,days=7"`
- "Show my runs last 2 weeks" → `"chart_type=activity_bars,days=14"`
- "Weekly running volume" → `"metric=distance_km,chart_type=weekly,weeks=8"`
- "Show my last run splits" → `"chart_type=activity"`
- "Give me an overview" → `"chart_type=dashboard"`

## Output guidance

- Keep interpretation short and actionable (2-4 sentences).
- Highlight the single most important signal.
- Mention uncertainty or data gaps if fewer than 5 data points.

## Edge cases

- If `render_chart` returns an error with available metrics listed, pick the closest match and retry once.
- If charts are disabled (`ENABLE_CHARTS=false`), summarise the trend in text instead.
- If data is unavailable, tell the user clearly rather than generating an empty chart.
