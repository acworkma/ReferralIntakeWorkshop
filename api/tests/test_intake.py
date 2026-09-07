"""The trigger-driven pipeline: what happens when a blob lands, not when an API is called."""

import base64
import json
from pathlib import Path
import uuid

import pytest
from sqlalchemy import select

from referral import intake
from referral.config import settings
from referral.database import Referral, SessionLocal
from referral.storage import store_incoming


def _blob_created_event(storage_uri: str, filename: str) -> str:
    return json.dumps(
        {
            "id": str(uuid.uuid4()),
            "eventType": "Microsoft.Storage.BlobCreated",
            "subject": f"/blobServices/default/containers/{settings.incoming_container}"
            f"/blobs/{filename}",
            "data": {"api": "PutBlob", "url": storage_uri},
        }
    )


def _landing_zone(container: str) -> Path:
    return Path(settings.local_landing_zone_root).resolve() / container


def _drop(filename: str, content: bytes, metadata: dict[str, str] | None = None) -> str:
    return store_incoming(filename, content, metadata=metadata)


def test_a_blob_landing_in_incoming_creates_a_referral_nobody_asked_for():
    """The whole point: no API call, no upload, just a document appearing in storage."""
    uri = _drop("upstream-drop.pdf", b"%PDF an upstream referral")

    referral_id = intake.handle_event(_blob_created_event(uri, "upstream-drop.pdf"))

    assert referral_id
    with SessionLocal() as session:
        referral = session.get(Referral, referral_id)
        assert referral.status == "needs_review"
        assert referral.filename == "upstream-drop.pdf"
        # Nothing told the pipeline who sent this, so it says so plainly.
        assert referral.submitted_by == "Upstream system"
        assert referral.source == "upstream"


def test_the_document_moves_out_of_incoming_as_it_is_processed():
    uri = _drop("moves-along.pdf", b"%PDF a document that moves")

    referral_id = intake.handle_event(_blob_created_event(uri, "moves-along.pdf"))

    assert not (_landing_zone(settings.incoming_container) / "moves-along.pdf").exists()
    assert (
        _landing_zone(settings.processing_container) / referral_id / "moves-along.pdf"
    ).exists()


def test_metadata_from_the_simulator_identifies_who_delivered_the_document():
    uri = _drop(
        "with-metadata.pdf",
        b"%PDF a document with provenance",
        metadata={"submittedby": "Dana Reviewer", "source": "web-simulator"},
    )

    referral_id = intake.handle_event(_blob_created_event(uri, "with-metadata.pdf"))

    with SessionLocal() as session:
        referral = session.get(Referral, referral_id)
        assert referral.submitted_by == "Dana Reviewer"
        assert referral.source == "web-simulator"


def test_a_document_that_is_not_a_referral_is_quarantined_not_ingested():
    uri = _drop("not-a-document.pdf", b"this is plain text, not a PDF")

    referral_id = intake.handle_event(_blob_created_event(uri, "not-a-document.pdf"))

    assert referral_id is None
    assert not (_landing_zone(settings.incoming_container) / "not-a-document.pdf").exists()
    quarantined = list(_landing_zone(settings.failed_container).rglob("not-a-document.pdf"))
    assert quarantined, "A rejected document must still be findable in the failed container."
    with SessionLocal() as session:
        assert not session.scalar(
            select(Referral).where(Referral.filename == "not-a-document.pdf")
        )


def test_the_same_document_twice_is_quarantined_as_a_duplicate():
    body = b"%PDF a document delivered twice"
    first = intake.handle_event(
        _blob_created_event(_drop("original.pdf", body), "original.pdf")
    )
    assert first

    second = intake.handle_event(_blob_created_event(_drop("copy.pdf", body), "copy.pdf"))

    assert second is None
    assert list(_landing_zone(settings.failed_container).rglob("copy.pdf"))


def test_an_upstream_filename_is_normalised_rather_than_rejected():
    """Upstream systems name files whatever they like; rejecting them loses referrals."""
    uri = _drop("Referral - Smith, John (2031).pdf", b"%PDF an awkwardly named referral")

    referral_id = intake.handle_event(
        _blob_created_event(uri, "Referral - Smith, John (2031).pdf")
    )

    with SessionLocal() as session:
        assert session.get(Referral, referral_id).filename == "Referral-Smith-John-2031-.pdf"


def test_a_redelivered_event_for_an_already_claimed_document_is_a_no_op():
    """Event Grid retries. The second delivery must not create a second referral."""
    uri = _drop("delivered-twice.pdf", b"%PDF a document whose event is redelivered")
    event = _blob_created_event(uri, "delivered-twice.pdf")

    first = intake.handle_event(event)
    second = intake.handle_event(event)

    assert first
    assert second is None


def test_extraction_failure_routes_the_document_to_failed_with_a_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "referral.processing.compare",
        lambda *_: (_ for _ in ()).throw(RuntimeError("Document Intelligence timed out")),
    )
    uri = _drop("breaks.pdf", b"%PDF a document that breaks extraction")

    referral_id = intake.handle_event(_blob_created_event(uri, "breaks.pdf"))

    assert referral_id is None
    with SessionLocal() as session:
        referral = session.scalar(select(Referral).where(Referral.filename == "breaks.pdf"))
        assert referral.status == "failed"
        assert "timed out" in referral.failure_reason
    assert list(_landing_zone(settings.failed_container).rglob("breaks.pdf"))


def test_events_for_other_containers_are_ignored():
    """Only the landing zone starts work; blobs we move ourselves must not re-trigger."""
    event = json.dumps(
        {
            "eventType": "Microsoft.Storage.BlobCreated",
            "data": {
                "url": (
                    Path(settings.local_landing_zone_root).resolve()
                    / settings.archive_container
                    / "something.pdf"
                ).as_uri()
            },
        }
    )

    assert intake.handle_event(event) is None


def test_unrelated_event_types_are_ignored():
    event = json.dumps(
        {"eventType": "Microsoft.Storage.BlobDeleted", "data": {"url": "file:///nowhere.pdf"}}
    )

    assert intake.handle_event(event) is None


def test_a_malformed_queue_message_does_not_crash_the_function():
    assert intake.handle_event("not json at all") is None


def test_a_base64_queue_message_is_decoded():
    """Event Grid base64-encodes the event when it writes to a storage queue."""
    uri = _drop("base64-drop.pdf", b"%PDF delivered through the queue")
    event = _blob_created_event(uri, "base64-drop.pdf")

    referral_id = intake.handle_event(base64.b64encode(event.encode("utf-8")))

    assert referral_id
    with SessionLocal() as session:
        assert session.get(Referral, referral_id).filename == "base64-drop.pdf"
