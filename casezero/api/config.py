"""Typed settings, loaded once from casezero/.env.

Both `LLM_PROVIDER` and `CASEZERO_LLM_PROVIDER` are accepted, and Gemini's key is
read from either `GOOGLE_API_KEY` or `GEMINI_API_KEY`, because the google-genai SDK
looks for its own names and we would rather tolerate both than have a silent
mismatch between what is in .env and what the SDK actually reads.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ─── LLM ────────────────────────────────────────────────────────────────
    llm_provider: str = "gemini"
    casezero_llm_provider: str | None = None

    google_api_key: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"

    groq_api_key: str | None = None
    # The Groq SDK appends /openai/v1 itself. Supplying that suffix here would
    # produce /openai/v1/openai/v1/chat/completions at runtime.
    groq_base_url: str = "https://api.groq.com"
    groq_model: str = "llama-3.3-70b-versatile"
    groq_model_fast: str = "llama-3.1-8b-instant"

    hunyuan_api_key: str | None = None
    hunyuan_base_url: str = "https://api.hunyuan.cloud.tencent.com/v1"
    hunyuan_model: str = "hunyuan-turbos-latest"

    # ─── Supabase ───────────────────────────────────────────────────────────
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None
    database_url: str | None = None
    supabase_access_token: str | None = None
    supabase_project_ref: str | None = None
    supabase_evidence_bucket: str = "evidence"

    # ─── MCP ────────────────────────────────────────────────────────────────
    #: stdio  -> agents talk to mcp_servers/ over the real protocol (default)
    #: inproc -> same tool functions called directly, for tests and offline runs
    mcp_transport: str = "stdio"
    #: If a server fails to spawn mid-demo, fall back rather than lose the run.
    mcp_allow_fallback: bool = True

    # ─── Security ───────────────────────────────────────────────────────────
    fernet_key: str | None = None
    #: A classification the model is unsure about must never auto-resolve.
    classifier_confidence_floor: float = Field(default=0.75, ge=0.0, le=1.0)

    # ─── Channels ───────────────────────────────────────────────────────────
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    complaints_email: str | None = None
    complaints_app_password: str | None = None
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    workbuddy_intake_token: str | None = None
    telegram_bot_token: str | None = None

    # ─── Web Push ───────────────────────────────────────────────────────────
    vapid_public_key: str | None = None
    vapid_private_key: str | None = None
    vapid_subject: str = "mailto:complaints@mybank.com.my"

    # ─── App ────────────────────────────────────────────────────────────────
    api_base_url: str = "http://localhost:8000"
    dashboard_base_url: str = "http://localhost:3000"
    bank_name: str = "MYBank Berhad"
    bank_complaints_email: str = "complaints@mybank.com.my"
    supervisor_interval_minutes: int = Field(default=15, ge=1, le=1440)

    # ─── Demo ───────────────────────────────────────────────────────────────
    demo_replay: bool = False
    demo_speed: float = 1.0
    #: Public judges may run an allow-listed synthetic complaint through the
    #: deployed stack. It is off by default so a cloned bank deployment cannot
    #: accidentally expose a metered endpoint.
    public_live_demo_enabled: bool = False
    public_live_demo_daily_limit: int = Field(default=24, ge=1, le=200)
    public_live_demo_hourly_limit: int = Field(default=2, ge=1, le=10)
    #: Shared only by the four synthetic staff accounts created by seed_users.
    #: It has no default so an operator cannot accidentally ship a known password.
    demo_user_password: str | None = None

    # ─── Derived ────────────────────────────────────────────────────────────

    @property
    def active_provider(self) -> str:
        """CASEZERO_LLM_PROVIDER wins if set, so a demo can be redirected with one var."""
        return (self.casezero_llm_provider or self.llm_provider or "gemini").lower()

    @property
    def gemini_key(self) -> str | None:
        return self.google_api_key or self.gemini_api_key

    @model_validator(mode="after")
    def _export_sdk_env(self) -> "Settings":
        """Mirror the Gemini key into the env names the google-genai SDK looks for.

        The SDK constructs its own client from the environment in some code paths,
        so leaving these unset produces confusing auth failures even when .env is
        correct.
        """
        key = self.gemini_key
        if key:
            os.environ["GOOGLE_API_KEY"] = key
            # The SDK warns when both names are present, so keep exactly one.
            os.environ.pop("GEMINI_API_KEY", None)
        return self

    def require(self, *names: str) -> None:
        """Fail loudly and specifically instead of deep inside an SDK call."""
        missing = [n for n in names if not getattr(self, n, None)]
        if missing:
            raise RuntimeError(
                "Missing required settings: "
                + ", ".join(n.upper() for n in missing)
                + f"\nExpected in {ENV_FILE}"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
