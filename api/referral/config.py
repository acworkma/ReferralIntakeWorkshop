from dataclasses import dataclass
import os


def _flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./referrals.db")
    local_mock_identity: bool = _flag("LOCAL_MOCK_IDENTITY")
    allow_local_mock_extraction: bool = _flag("ALLOW_LOCAL_MOCK_EXTRACTION")
    upload_max_bytes: int = int(os.getenv("UPLOAD_MAX_BYTES", str(10 * 1024 * 1024)))
    cors_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    )
    storage_account_url: str | None = os.getenv("STORAGE_ACCOUNT_URL")
    queue_account_url: str | None = os.getenv("QUEUE_ACCOUNT_URL")
    queue_name: str = os.getenv("QUEUE_NAME", "referral-jobs")
    queue_worker_enabled: bool = _flag("QUEUE_WORKER_ENABLED", True)
    queue_batch_size: int = int(os.getenv("QUEUE_BATCH_SIZE", "4"))
    queue_poll_seconds: float = float(os.getenv("QUEUE_POLL_SECONDS", "5"))
    queue_visibility_timeout: int = int(os.getenv("QUEUE_VISIBILITY_TIMEOUT", "300"))
    queue_max_dequeue: int = int(os.getenv("QUEUE_MAX_DEQUEUE", "5"))
    queue_shutdown_seconds: float = float(os.getenv("QUEUE_SHUTDOWN_SECONDS", "10"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    document_intelligence_endpoint: str | None = os.getenv("DOCUMENT_INTELLIGENCE_ENDPOINT")
    content_understanding_endpoint: str | None = os.getenv("CONTENT_UNDERSTANDING_ENDPOINT")
    content_understanding_analyzer: str = os.getenv(
        "CONTENT_UNDERSTANDING_ANALYZER", "prebuilt-document"
    )
    content_understanding_api_version: str = os.getenv(
        "CONTENT_UNDERSTANDING_API_VERSION", "2025-11-01"
    )

    def validate(self) -> None:
        if os.getenv("WEBSITE_INSTANCE_ID") and (
            self.local_mock_identity or self.allow_local_mock_extraction
        ):
            raise RuntimeError("Local-only identity and extraction modes are forbidden in Azure.")


settings = Settings()
settings.validate()
