from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str
    bot_name: str = ""
    owner_ids: str = ""
    secret_key: str
    database_url: str
    redis_url: str

    update_mode: str = "polling"
    webhook_url: str = ""
    webhook_secret: str = ""
    webhook_path: str = "/webhook"
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8080

    alert_chat_id: int | None = None
    log_level: str = "INFO"
    environment: str = "production"

    rate_limit_private_per_sec: float = 25.0
    rate_limit_callback_per_sec: float = 40.0
    purchase_lock_ttl_sec: int = 20
    invoice_ttl_sec: int = 1800
    max_broadcast_per_sec: float = 25.0

    @field_validator("alert_chat_id", mode="before")
    @classmethod
    def empty_alert_chat(cls, value: object) -> object:
        if value in ("", None):
            return None
        return value

    @field_validator("secret_key")
    @classmethod
    def secret_must_be_long(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return value

    @property
    def owners(self) -> frozenset[int]:
        ids: set[int] = set()
        for part in self.owner_ids.split(","):
            part = part.strip()
            if part:
                ids.add(int(part))
        return frozenset(ids)

    @property
    def is_webhook(self) -> bool:
        return self.update_mode.lower() == "webhook"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
