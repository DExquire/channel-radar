"""Application settings, loaded once from environment / .env.

Kept deliberately small: everything that differs between local and cloud
(DB URL, LLM key, cron secret) is an env var so the same image runs anywhere.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Storage ---------------------------------------------------------
    # Local default is SQLite so the project runs with zero setup.
    # In the cloud DATABASE_URL points at Postgres (Neon / Render).
    database_url: str = "sqlite:///./channel_radar.db"

    # --- Collection ------------------------------------------------------
    tme_base_url: str = "https://t.me/s"
    http_timeout_seconds: float = 15.0
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    )
    # How often the in-process scheduler refreshes channels (used only when
    # RUN_SCHEDULER=1, e.g. on always-on hosts like Fly). On sleeping hosts
    # (Render free) collection is driven by the external cron endpoint instead.
    run_scheduler: bool = False
    collect_interval_minutes: int = 30
    # Skip re-collecting a channel touched within this window (idempotent + cheap).
    min_recollect_minutes: int = 5

    # --- AI layer --------------------------------------------------------
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    ai_timeout_seconds: float = 30.0

    # --- Security --------------------------------------------------------
    # Shared secret the external cron trigger must present to POST /api/cron/collect.
    cron_secret: str = ""

    @property
    def ai_enabled(self) -> bool:
        return bool(self.gemini_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
