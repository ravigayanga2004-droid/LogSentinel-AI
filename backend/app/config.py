import secrets
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: str = "development"
    database_url: str = "sqlite:///./data/logsentinel.db"
    secret_key: str = ""
    cookie_secure: bool = False
    public_origin: str = "http://localhost:5173"
    upload_max_bytes: int = 10 * 1024 * 1024
    session_hours: int = 12
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "logsentinel@localhost"
    smtp_tls: bool = True

    @model_validator(mode="after")
    def production_guard(self):
        if self.environment == "production":
            if len(self.secret_key) < 32 or self.secret_key.startswith("replace-"):
                raise ValueError("Production requires a fresh SECRET_KEY of at least 32 characters")
            if not self.cookie_secure or not self.public_origin.startswith("https://"):
                raise ValueError("Production requires secure cookies and an HTTPS public origin")
            if not self.database_url.startswith("postgresql"):
                raise ValueError("Production requires PostgreSQL")
        if not self.secret_key:
            # Local only: persistent deployments MUST configure a stable key for entity correlation.
            self.secret_key = secrets.token_hex(32)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
