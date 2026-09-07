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
    # Box 3 landing zone. A referral's container is its workflow state.
    incoming_container: str = os.getenv("INCOMING_CONTAINER", "incoming")
    processing_container: str = os.getenv("PROCESSING_CONTAINER", "processing")
    failed_container: str = os.getenv("FAILED_CONTAINER", "failed")
    archive_container: str = os.getenv("ARCHIVE_CONTAINER", "archive")
    # Stands in for the storage account when one is not configured, so the same
    # pipeline code runs on a laptop instead of a second untested code path.
    local_landing_zone_root: str = os.getenv("LOCAL_LANDING_ZONE_ROOT", "./.landingzone")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    # Box 5 business rules. Left unset, notifications are logged and skipped so
    # the pipeline still runs end to end without the Logic App configured.
    logic_app_url: str | None = os.getenv("LOGIC_APP_URL")
    document_intelligence_endpoint: str | None = os.getenv("DOCUMENT_INTELLIGENCE_ENDPOINT")
    content_understanding_endpoint: str | None = os.getenv("CONTENT_UNDERSTANDING_ENDPOINT")
    content_understanding_analyzer: str = os.getenv(
        # Content Understanding rejects '-' in analyzer IDs.
        "CONTENT_UNDERSTANDING_ANALYZER",
        "referralIntake",
    )
    content_understanding_api_version: str = os.getenv(
        "CONTENT_UNDERSTANDING_API_VERSION", "2025-11-01"
    )
    content_understanding_completion_model: str = os.getenv(
        "CONTENT_UNDERSTANDING_COMPLETION_MODEL", "gpt-5.2"
    )
    content_understanding_embedding_model: str = os.getenv(
        "CONTENT_UNDERSTANDING_EMBEDDING_MODEL", "text-embedding-3-large"
    )
    content_understanding_completion_deployment: str = os.getenv(
        "CONTENT_UNDERSTANDING_COMPLETION_DEPLOYMENT", "gpt-5.2"
    )
    content_understanding_embedding_deployment: str = os.getenv(
        "CONTENT_UNDERSTANDING_EMBEDDING_DEPLOYMENT", "text-embedding-3-large"
    )

    def validate(self) -> None:
        if os.getenv("WEBSITE_INSTANCE_ID") and (
            self.local_mock_identity or self.allow_local_mock_extraction
        ):
            raise RuntimeError("Local-only identity and extraction modes are forbidden in Azure.")


settings = Settings()
settings.validate()
