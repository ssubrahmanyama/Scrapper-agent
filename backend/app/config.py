"""config.py — All settings via env / Vault. Zero proprietary SDKs."""
from __future__ import annotations
import secrets
from typing import Any, List, Optional
from pydantic import AnyHttpUrl, EmailStr, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=True)
    APP_NAME: str = "PrivacyShield API"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "production"
    DEBUG: bool = False
    SECRET_KEY: str = secrets.token_urlsafe(64)
    API_V1_PREFIX: str = "/api/v1"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALGORITHM: str = "HS256"
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []
    ALLOWED_HOSTS: List[str] = ["privacyshield.local", "localhost"]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors(cls, v: Any) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        return v

    DATABASE_URL: PostgresDsn
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 40
    DATABASE_ECHO: bool = False
    REDIS_URL: RedisDsn
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str
    # SearXNG replaces Google Custom Search
    SEARXNG_URL: str = "http://searxng:8080"
    # SMTP replaces SendGrid
    SMTP_HOST: str = "mailhog"
    SMTP_PORT: int = 1025
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_USE_TLS: bool = False
    SMTP_STARTTLS: bool = False
    FROM_EMAIL: EmailStr = "noreply@privacyshield.local"
    FROM_NAME: str = "PrivacyShield"
    # MinIO replaces AWS S3
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "privacyshield-exports"
    MINIO_SECURE: bool = False
    # Vault replaces AWS Secrets Manager
    VAULT_ADDR: str = "http://vault:8200"
    VAULT_TOKEN: Optional[str] = None
    VAULT_SECRET_PATH: str = "privacyshield/production"
    # GlitchTip replaces Sentry SaaS (same SDK wire protocol)
    SENTRY_DSN: Optional[str] = None
    # Crawler
    CRAWLER_MAX_PAGES: int = 100
    CRAWLER_TIMEOUT_SECONDS: int = 30
    CRAWLER_USER_AGENT: str = "PrivacyShieldBot/1.0 (+https://privacyshield.local/bot)"
    DATA_BROKER_LIST_PATH: str = "data/data_brokers.json"
    RESCAN_INTERVAL_HOURS: int = 168
    # NLP
    SPACY_MODEL: str = "en_core_web_trf"
    NLP_CONFIDENCE_THRESHOLD: float = 0.85
    RATE_LIMIT_PER_MINUTE: int = 60
    ENABLE_BROWSER_EXTENSION_API: bool = True
    ENABLE_ENTERPRISE_API: bool = True

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

settings = Settings()  # type: ignore[call-arg]
