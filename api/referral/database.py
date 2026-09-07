from datetime import datetime, timezone
import json
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, Text, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import settings


class Base(DeclarativeBase):
    pass


class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    submitted_by: Mapped[str] = mapped_column(String(255))
    storage_uri: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="upstream")
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    comparison_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    review_note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def response(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "filename": self.filename,
            "status": self.status,
            "progress": self.progress,
            "submittedBy": self.submitted_by,
            "source": self.source,
            "container": self.container(),
            "failureReason": self.failure_reason,
            "comparison": json.loads(self.comparison_json) if self.comparison_json else None,
            "approved": self.approved,
            "reviewNote": self.review_note,
            "reviewedBy": self.reviewed_by,
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
        }

    def container(self) -> str | None:
        """The landing zone container holding this document right now.

        A referral's container is its state, so surfacing it is what lets the
        review UI show where a document physically sits rather than only what
        the database believes about it.
        """
        if not self.storage_uri:
            return None
        # Imported lazily: storage pulls in the Azure SDKs, and the model is
        # imported by tooling that has no reason to load them.
        from .storage import split_blob_uri

        try:
            return split_blob_uri(self.storage_uri)[0]
        except (ValueError, IndexError):
            return None


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
pool_options = (
    {"poolclass": StaticPool}
    if settings.database_url in {"sqlite://", "sqlite:///:memory:"}
    else {}
)
engine = create_engine(
    settings.database_url, connect_args=connect_args, pool_pre_ping=True, **pool_options
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


def _add_missing_columns() -> None:
    """Add columns the model has gained since the table was first created.

    create_all() only creates tables that do not exist, so a workshop
    environment deployed against an earlier schema keeps an old table forever.
    This is additive only: it never drops or retypes anything, which keeps a
    redeploy safe to run against a database that already holds referrals.
    """
    inspector = inspect(engine)
    if not inspector.has_table(Referral.__tablename__):
        return
    existing = {column["name"] for column in inspector.get_columns(Referral.__tablename__)}
    missing = [column for column in Referral.__table__.columns if column.name not in existing]
    if not missing:
        return
    compiler = engine.dialect.type_compiler_instance
    with engine.begin() as connection:
        for column in missing:
            definition = f"{column.name} {compiler.process(column.type)} NULL"
            connection.execute(
                text(f"ALTER TABLE {Referral.__tablename__} ADD {definition}")
            )
        if any(column.name == "source" for column in missing):
            connection.execute(
                text(f"UPDATE {Referral.__tablename__} SET source = 'upstream' WHERE source IS NULL")
            )
