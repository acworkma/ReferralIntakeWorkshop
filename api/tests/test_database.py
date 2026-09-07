"""The schema has to survive a redeploy over an existing workshop database."""

from datetime import datetime, timezone

from sqlalchemy import inspect, text

from referral import database


def test_initialize_adds_columns_the_model_gained_since_the_table_was_created():
    with database.engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS referrals"))
        connection.execute(
            text(
                """
                CREATE TABLE referrals (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    filename VARCHAR(255) NOT NULL,
                    sha256 VARCHAR(64) NOT NULL UNIQUE,
                    status VARCHAR(32) NOT NULL,
                    progress INTEGER NOT NULL,
                    submitted_by VARCHAR(255) NOT NULL,
                    storage_uri VARCHAR(2048),
                    comparison_json TEXT,
                    approved BOOLEAN,
                    review_note VARCHAR(2000),
                    reviewed_by VARCHAR(255),
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                "INSERT INTO referrals (id, filename, sha256, status, progress, submitted_by,"
                " created_at, updated_at) VALUES ('old', 'prior.pdf', 'abc', 'needs_review', 100,"
                " 'someone', '2024-01-01 00:00:00', '2024-01-01 00:00:00')"
            )
        )

    database.initialize_database()

    columns = {column["name"] for column in inspect(database.engine).get_columns("referrals")}
    assert {"source", "failure_reason"} <= columns

    with database.SessionLocal() as session:
        # The row that predates the migration is still there, and still readable
        # through the model that gained the columns.
        row = session.get(database.Referral, "old")
        assert row is not None
        assert row.filename == "prior.pdf"
        assert row.source == "upstream"


def test_initialize_is_safe_to_run_twice():
    database.initialize_database()
    database.initialize_database()
    columns = {column["name"] for column in inspect(database.engine).get_columns("referrals")}
    assert "failure_reason" in columns


def test_response_reports_the_container_the_document_is_in():
    """The container is the referral's state, so the API has to surface it."""
    referral = database.Referral(
        id="c1",
        filename="referral.pdf",
        sha256="hash",
        status="needs_review",
        progress=100,
        submitted_by="someone",
        storage_uri="https://example.blob.core.windows.net/processing/c1/referral.pdf",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    assert referral.response()["container"] == "processing"


def test_response_reports_no_container_before_the_document_is_claimed():
    referral = database.Referral(
        id="c2",
        filename="referral.pdf",
        sha256="hash2",
        status="queued",
        progress=0,
        submitted_by="someone",
        storage_uri=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    assert referral.response()["container"] is None
