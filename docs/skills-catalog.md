# Skills Catalog

ADK filesystem skills live in `apps/garmin_coach/skills/`. Each skill is a Markdown file with YAML frontmatter declaring its name, description, and which registered tools it activates via `metadata.adk_additional_tools`.

## Inventory

| Skill | Trigger intent | Activates tool | Risk level |
|---|---|---|---|
| `coach-context` | "how am I doing", "give me a summary", "what's my status" | `get_context_data` | read-only |
| `fitness-analysis` | "analyze my fitness", "am I overtraining", "show trends" | `analyze_fitness` | read-only |
| `weekly-plan` | "what should I do next week", "build me a plan", "training schedule" | `weekly_plan` | read-only |
| `query-data-guarded` | specific data questions, "how far did I run", "what was my HR" | `query_data` | guarded (NL2SQL) |
| `chart-render` | "show me a chart", "visualize my sleep", "plot my runs" | `render_chart` | read-only |

## Skill Details

### `coach-context`
Assembles a structured fitness context snapshot: profile, active goals, last 7 days of daily summaries, and recent activities. Used as a preamble for coaching replies or standalone status checks.

**Tool:** `get_context_data(days, activities_limit)` → JSON payload

---

### `fitness-analysis`
Runs deterministic trend analysis on recent load, sleep, heart rate, and fatigue indicators. Applies Norwegian method heuristics to flag overtraining risk or under-recovery.

**Tool:** `analyze_fitness(analysis_type, days)` → structured analysis payload

---

### `weekly-plan`
Builds a safe next-week training plan based on the user's stated goal, last week's load, and Norwegian-method progression rules (85% easy volume, 1 quality session, conservative 10% weekly increase cap).

**Tool:** `weekly_plan(goal_description, norwegian_method, max_hours_per_week)` → session outline + constraints

---

### `query-data-guarded`
Answers specific factual data questions by translating them to parameterized SQL and executing against the Garmin data tables. All queries are validated by the NL2SQL guardrails layer before execution.

**Safety policy:**
- `SELECT`-only, single statement
- Blocked keywords: `DROP`, `DELETE`, `UPDATE`, `INSERT`, `EXEC`, `UNION`, `--`
- Allowed tables: `garmin_activities`, `garmin_daily_summaries`, `garmin_sleep_data`, `heart_rate_measurements`
- Mandatory `:user_id` parameter (cross-user data access is structurally impossible)
- `LIMIT ≤ 200` enforced (waived for aggregate functions: `SUM`, `COUNT`, `AVG`, `MIN`, `MAX`)
- `SET LOCAL statement_timeout` applied per query

**Tool:** `query_data(question)` → rows or aggregate result

---

### `chart-render`
Generates a PNG chart image and delivers it directly to Telegram. The agent composes a spec string (`key=value`) based on user intent; the chart tool selects the appropriate builder and rendering style.

**Chart types:**

| `chart_type` | Description | Best for |
|---|---|---|
| `trend` | Line + area fill, rolling 7-day avg | Continuous metrics: HR, VO2max, stress |
| `bar` | Daily bars, baseline reference | Discrete daily values: sleep, calories |
| `weekly` | ISO-week aggregated bars, 3-week avg | Volume trends over multiple weeks |
| `activity_bars` | One bar per individual run, value labels | "Show me each run last 2 weeks" |
| `activity` | Split pace + HR for a single run | Post-run analysis |
| `dashboard` | 3-panel overview (steps, sleep/HR, distance) | General overview |

**Tool:** `render_chart(chart_request)` → `chart_path` + `caption`
