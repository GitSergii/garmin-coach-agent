"""Runner + persistent session wiring for ADK coach."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types

from coach_adk.agent import root_agent, APP_STATE_USER_KEY
from core.config import Config

DEFAULT_APP_NAME = "garmin_coach_adk"
DEFAULT_SESSION_ID = "default"
DEFAULT_SESSION_DB_URL = "sqlite+aiosqlite:///./data/adk_sessions.db"
ALLOWED_ASYNC_SCHEMES = (
    "sqlite+aiosqlite://",
    "postgresql+asyncpg://",
    "mysql+aiomysql://",
    "mariadb+aiomysql://",
)


@dataclass
class CoachResponse:
    """Normalized coach response contract consumed by Telegram handlers."""

    text: str
    tools_used: List[str]
    response_time_ms: float
    confidence_score: Optional[float] = None
    has_charts: bool = False
    chart_data: Optional[Dict[str, Any]] = None
    tokens_used: Optional[int] = None


def _validate_async_db_url_or_fail(db_url: str) -> None:
    if not db_url.startswith(ALLOWED_ASYNC_SCHEMES):
        raise RuntimeError(
            "Invalid ADK_SESSION_DB_URL async driver. Use one of: "
            + ", ".join(ALLOWED_ASYNC_SCHEMES)
        )


def _resolve_session_db_config() -> tuple[str, str, bool]:
    db_url = os.getenv("ADK_SESSION_DB_URL", DEFAULT_SESSION_DB_URL).strip()
    app_name = os.getenv("ADK_SESSION_APP_NAME", DEFAULT_APP_NAME).strip() or DEFAULT_APP_NAME
    strict_startup = os.getenv("ADK_SESSION_STRICT_STARTUP", "true").lower() == "true"
    return db_url, app_name, strict_startup


class AdkCoachRuntime:
    """ADK Runner wiring with database-backed sessions and strict startup checks."""

    def __init__(self, config: Config) -> None:
        if not config.google_cloud.api_key:
            raise RuntimeError("GOOGLE_API_KEY is required for ADK runtime")

        if config.app.env != "development" and not os.getenv("ADK_SESSION_DB_URL"):
            raise RuntimeError(
                "ADK_SESSION_DB_URL is required outside development environment"
            )

        session_db_url, app_name, strict_startup = _resolve_session_db_config()
        self.app_name = app_name
        self.strict_startup = strict_startup
        self._total_requests = 0
        _validate_async_db_url_or_fail(session_db_url)

        try:
            session_service = DatabaseSessionService(db_url=session_db_url)
        except Exception as exc:  # noqa: BLE001 - startup hard-fail contract
            raise RuntimeError(f"Failed to initialize DatabaseSessionService: {exc}") from exc

        self._session_service = session_service
        self._runner = Runner(
            agent=root_agent,
            app_name=self.app_name,
            session_service=self._session_service,
            auto_create_session=True,
        )

    def get_performance_stats(self) -> Dict[str, Any]:
        return {"total_requests": self._total_requests, "backend": "adk"}

    async def session_smoke_check_or_fail(self) -> None:
        """Fail startup immediately if session DB wiring is not healthy."""
        test_user = "startup_smoke_user"
        smoke_session_id = f"smoke-{uuid.uuid4().hex[:12]}"
        session = await self._session_service.create_session(
            app_name=self.app_name,
            user_id=test_user,
            session_id=smoke_session_id,
            state={APP_STATE_USER_KEY: test_user},
        )
        if session is None:
            raise RuntimeError("Session service create_session returned None")
        loaded = await self._session_service.get_session(
            app_name=self.app_name,
            user_id=test_user,
            session_id=smoke_session_id,
        )
        if loaded is None:
            raise RuntimeError("Session service get_session returned None after create")

    async def _ensure_session(self, user_id: str) -> None:
        existing = await self._session_service.get_session(
            app_name=self.app_name,
            user_id=user_id,
            session_id=DEFAULT_SESSION_ID,
        )
        if existing:
            return
        await self._session_service.create_session(
            app_name=self.app_name,
            user_id=user_id,
            session_id=DEFAULT_SESSION_ID,
            state={APP_STATE_USER_KEY: user_id},
        )

    async def start_conversation(self, user_id: str) -> str:
        await self._ensure_session(user_id)
        return "Ready when you are. Ask for context, trends, a weekly plan, or a specific metric."

    async def _run_single_turn(
        self, user_id: str, message: str
    ) -> Tuple[List[str], List[str], Dict[str, Any] | None]:
        content = types.Content(role="user", parts=[types.Part(text=message)])
        tools_used: List[str] = []
        assembled: List[str] = []
        chart_data: Dict[str, Any] | None = None

        async for event in self._runner.run_async(
            user_id=user_id,
            session_id=DEFAULT_SESSION_ID,
            new_message=content,
            state_delta={APP_STATE_USER_KEY: user_id},
        ):
            for fc in event.get_function_calls() or []:
                if getattr(fc, "name", None):
                    tools_used.append(str(fc.name))
            for fr in event.get_function_responses() or []:
                tool_name = getattr(fr, "name", "")
                payload = getattr(fr, "response", None)
                # ADK wraps string returns as {"result": "<json_string>"} — unwrap first.
                if isinstance(payload, dict) and "result" in payload and isinstance(payload["result"], str):
                    try:
                        payload = json.loads(payload["result"])
                    except json.JSONDecodeError:
                        pass
                elif isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except json.JSONDecodeError:
                        payload = {"raw": payload}
                if tool_name == "render_chart" and isinstance(payload, dict):
                    if payload.get("chart_path"):
                        chart_data = payload
            if not event.is_final_response():
                continue
            if not event.content or not event.content.parts:
                continue
            for part in event.content.parts:
                if part.text:
                    assembled.append(part.text)

        return tools_used, assembled, chart_data

    async def process_message(self, user_id: str, message: str) -> CoachResponse:
        started = datetime.utcnow()
        self._total_requests += 1
        await self._ensure_session(user_id)

        tools_used, assembled, chart_data = await self._run_single_turn(user_id, message)

        elapsed_ms = (datetime.utcnow() - started).total_seconds() * 1000.0
        text_out = "\n".join(assembled).strip() or "(No textual reply from model.)"
        return CoachResponse(
            text=text_out,
            tools_used=list(dict.fromkeys(tools_used)),
            response_time_ms=elapsed_ms,
            confidence_score=None,
            has_charts=bool(chart_data),
            chart_data=chart_data,
            tokens_used=None,
        )

    async def end_conversation(self, user_id: str) -> None:
        _ = user_id


def init_adk_coach_runtime(config: Config) -> AdkCoachRuntime:
    return AdkCoachRuntime(config)


async def init_adk_coach_runtime_async(config: Config) -> AdkCoachRuntime:
    runtime = AdkCoachRuntime(config)
    if runtime.strict_startup:
        await runtime.session_smoke_check_or_fail()
    return runtime
