"""Application settings, read from the environment (see .env.example)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core
    database_url: str = "sqlite:///./orbit.db"
    tz: str = "Asia/Kuala_Lumpur"
    demo_mode: bool = True

    # Secrets
    session_secret: str = "change-me"
    phone_hmac_key: str = "change-me"
    phone_enc_key: str = ""

    # Receipt extraction, the only place AI is used
    llm_provider: str = "mock"
    anthropic_api_key: str = ""

    # WhatsApp Cloud API. All optional: with none of these set, Orbit runs on the
    # built-in simulator, which uses the same webhook payload shape.
    whatsapp_verify_token: str = "orbit-verify"
    whatsapp_app_secret: str = ""
    whatsapp_token: str = ""
    whatsapp_phone_id: str = ""

    @property
    def whatsapp_live(self) -> bool:
        """True only when a real Cloud API channel is actually configured."""
        return bool(self.whatsapp_token and self.whatsapp_phone_id)

    @property
    def using_placeholder_secrets(self) -> bool:
        """True when the app is running on the .env.example placeholders."""
        return "change-me" in (self.session_secret, self.phone_hmac_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
