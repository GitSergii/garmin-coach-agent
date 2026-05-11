"""Shared NL2SQL validation policy and read-only execution helpers."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from core.database import Database

ALLOWED_TABLES = {
    "garmin_daily_summaries",
    "garmin_activities",
    "garmin_sleep",
    "garmin_heart_rate",
}


def validate_nl2sql_query(sql_query: str) -> Optional[str]:
    """Validate model-generated SQL against strict read-only policy."""
    lowered = sql_query.lower().strip()

    if ";" in sql_query.strip().rstrip(";"):
        return "NL2SQL rejected: multiple SQL statements are not allowed."
    if not lowered.startswith("select"):
        return "NL2SQL rejected: only SELECT queries are allowed."
    if "--" in lowered or "/*" in lowered or "*/" in lowered:
        return "NL2SQL rejected: SQL comments are not allowed."

    blocked_tokens = [
        " insert ",
        " update ",
        " delete ",
        " drop ",
        " alter ",
        " create ",
        " truncate ",
        " grant ",
        " revoke ",
        " execute ",
        " call ",
        " do ",
        " copy ",
        " attach ",
        " detach ",
    ]
    if any(token in f" {lowered} " for token in blocked_tokens):
        return "NL2SQL rejected: query contains blocked SQL operations."

    table_matches = re.findall(r"\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", lowered)
    disallowed = [table for table in table_matches if table not in ALLOWED_TABLES]
    if disallowed:
        return (
            "NL2SQL rejected: disallowed table(s) referenced: "
            + ", ".join(sorted(set(disallowed)))
            + "."
        )

    if ":user_id" not in lowered:
        return "NL2SQL rejected: query must include parameterized user_id filter (:user_id)."

    _AGGREGATE_FUNCTIONS = ("sum(", "count(", "avg(", "min(", "max(")
    is_aggregate = any(fn in lowered for fn in _AGGREGATE_FUNCTIONS)

    limit_match = re.search(r"\blimit\s+(\d+)\b", lowered)
    if limit_match:
        if int(limit_match.group(1)) > 200:
            return "NL2SQL rejected: LIMIT cannot exceed 200."
    elif not is_aggregate:
        return "NL2SQL rejected: query must include LIMIT <= 200."

    return None


def execute_readonly_query(
    database: Database, sql_query: str, user_id: str
) -> Dict[str, Any]:
    """Execute validated SELECT query with strict read-only constraints."""
    with database.get_session() as session:
        session.execute(text("SET LOCAL statement_timeout = 5000"))
        result = session.execute(text(sql_query), {"user_id": user_id})
        rows = result.fetchall()
        columns = list(result.keys())
        data: List[Dict[str, Any]] = [dict(zip(columns, row)) for row in rows]
    return {"query": sql_query, "data": data, "row_count": len(data)}
