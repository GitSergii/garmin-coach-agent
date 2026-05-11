# Garmin Coach

> **Google ADK-powered self-hosted Garmin coaching agent**

A single-user, self-hosted AI running coach that pulls data from Garmin Connect and delivers coaching, analysis, weekly plans, and charts through a private Telegram chat.

[![CI](https://github.com/GitSergii/Garmin-Coach/actions/workflows/ci.yml/badge.svg)](https://github.com/GitSergii/Garmin-Coach/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11-blue)
![ADK](https://img.shields.io/badge/Google_ADK-1.x-4285F4)
![Gemini](https://img.shields.io/badge/Gemini_2.5_Flash-enabled-green)

---

## What it does

Send a message to your private Telegram bot and get:

- **Coaching summaries** — daily fitness context assembled from Garmin data (steps, sleep, HR, activities, goals)
- **Fitness trend analysis** — load trends, fatigue signals, overtraining risk using Norwegian method heuristics
- **Weekly training plans** — conservative progression plans aligned to your goal (e.g. 100 km ultramarathon)
- **Natural-language data queries** — "How far did I run last week?" answered with guarded NL2SQL
- **Charts** — sleep bars, HR trends, weekly volume, per-run bars — delivered as images directly in chat

---

## Architecture

```
Telegram (private chat)
        │
        ▼
  TelegramBot                    single-owner access control
        │
        ▼
  AdkCoachRuntime                Google ADK Runner + DatabaseSessionService
        │
        ▼
  root_agent (Gemini 2.5 Flash)
        │
        ├── SkillToolset ──────── 5 filesystem skill files (Markdown)
        │
        ├── get_context_data      Garmin data snapshot
        ├── analyze_fitness       deterministic load + trend analysis
        ├── weekly_plan           Norwegian-method planning guardrails
        ├── query_data            NL2SQL with validation layer
        └── render_chart          spec-driven chart generation (6 types)
```

See [`docs/architecture.md`](docs/architecture.md) for full data flow and design decisions.

---

## Tech Stack

| Layer | Technology |
|---|---|
| AI agent runtime | [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/) |
| LLM | Gemini 2.5 Flash via `google-genai` |
| Agent skills | ADK filesystem `SkillToolset` (Markdown skill files) |
| Bot interface | `python-telegram-bot` 21.x |
| Data source | Garmin Connect via `garminconnect` library |
| Database | PostgreSQL (SQLite for local dev) |
| Session storage | ADK `DatabaseSessionService` (async driver required) |
| Charts | `matplotlib` + `pandas` |
| Package manager | [`uv`](https://github.com/astral-sh/uv) |

---

## Self-Hosted, Single-User Design

This project is intentionally scoped to one user per deployment:

- The first private Telegram message binds the bot to one owner
- All other users and chats are rejected with a one-line message
- Garmin credentials are encrypted at rest (Fernet / `SECRET_KEY`)
- No multi-tenant data model, no SaaS billing, no shared infrastructure

This simplifies the security model dramatically and makes the codebase easier to audit and trust.

---

## Quickstart

### Prerequisites

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) package manager
- PostgreSQL (or SQLite for local dev)
- Telegram bot token ([BotFather](https://t.me/botfather))
- Google AI API key ([Google AI Studio](https://aistudio.google.com/))
- Garmin Connect account

### Local setup

```bash
# 1. Clone and install
git clone https://github.com/GitSergii/Garmin-Coach.git
cd Garmin-Coach
uv venv --python 3.11
uv sync

# 2. Configure
cp .env.example .env
# Edit .env — fill GOOGLE_API_KEY, TELEGRAM_BOT_TOKEN, SECRET_KEY, DB_*

# 3. Run
./.venv/bin/python run.py
```

Send any private message to your Telegram bot. The first message binds you as the owner.

Run `/setup` to enter your Garmin credentials, then `/sync` to pull your data.

### Docker Compose

```bash
cp .env.example .env
# Edit .env
docker compose up --build
```

---

## Configuration

### Required

| Variable | Description |
|---|---|
| `GOOGLE_API_KEY` | Gemini API key |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `SECRET_KEY` | Long random string for credential encryption |
| `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | PostgreSQL connection |

### Access control

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_OWNER_USER_ID` | _(empty)_ | Pre-bind owner Telegram user ID |
| `TELEGRAM_OWNER_CHAT_ID` | _(empty)_ | Pre-bind owner chat ID |
| `TELEGRAM_BIND_ON_FIRST_START` | `true` | Bind owner on first private message |

**Production recommendation:** set `TELEGRAM_OWNER_USER_ID` and `TELEGRAM_OWNER_CHAT_ID` explicitly before exposing your bot username publicly, then set `TELEGRAM_BIND_ON_FIRST_START=false`.

### ADK sessions

| Variable | Default | Description |
|---|---|---|
| `ADK_SESSION_DB_URL` | `sqlite+aiosqlite:///./data/adk_sessions.db` | Session DB — must use async driver |
| `ADK_SESSION_STRICT_STARTUP` | `true` | Hard-fail on session DB error at startup |

### Feature flags

| Variable | Default | Description |
|---|---|---|
| `ENABLE_NL2SQL` | `true` | Enable natural-language data queries |
| `ENABLE_CHARTS` | `true` | Enable chart image generation |

---

## NL2SQL Safety

The `query_data` tool enforces a strict validation policy before executing any generated SQL:

- `SELECT`-only, single statement
- Blocked keywords: `DROP`, `DELETE`, `UPDATE`, `INSERT`, `EXEC`, `UNION`, `--`
- Allowed tables allowlist (only Garmin data tables)
- Mandatory parameterized `:user_id` filter (cross-user access structurally impossible)
- `LIMIT ≤ 200` (waived for aggregate functions)
- Per-query `statement_timeout` via `SET LOCAL`

---

## Development

```bash
# Run tests
./.venv/bin/python -m pytest tests/ apps/garmin_coach/tests/ -v

# Sync Garmin data manually
./.venv/bin/python sync_garmin_data.py
```

### Project structure

```
apps/garmin_coach/       ADK agent, skills, and ADK-specific tests
src/
  analytics/             deterministic analytics and NL2SQL
  core/                  Telegram bot, Garmin client, database models
  tools/                 data retrieval and chart generation
tests/                   pytest suite
docs/                    architecture and skills catalog
```

---

## Troubleshooting

**Bot doesn't respond**
Check that only one instance of `run.py` is running. The app uses a PID lock file (`.run/garmin-coach.pid`) to prevent duplicates.

**Garmin 429 Too Many Requests**
Garmin rate-limits repeated SSO authentication. After the first successful `/sync`, OAuth tokens are saved to `data/garmin_tokens/` so restarts no longer trigger a full password auth. If you hit 429, wait 15–30 minutes before syncing again.

**ADK session error on startup**
Ensure `ADK_SESSION_DB_URL` uses an async driver: `sqlite+aiosqlite://` or `postgresql+asyncpg://`. A sync driver URL will fail at startup.

**No activities in charts**
Run `/sync` first. Activity data is fetched from Garmin Connect and must be present in the local database before charts or weekly plans can use it.

---

## License

MIT — see [LICENSE](LICENSE).
