"""Box 5: what happens when a document lands in the storage account.

This module is the workflow. It is triggered by a blob landing in ``incoming``
and is deliberately independent of the web app: a document dropped by azcopy,
Storage Explorer, or a real upstream system takes exactly this path, because
this path starts at the blob rather than at an HTTP request.

The orchestration function is a thin wrapper over :func:`handle_event`.
"""

import base64
import binascii
from datetime import datetime, timezone
import json
import logging
import uuid

from azure.core.exceptions import ResourceNotFoundError
from sqlalchemy import select

from .config import settings
from .database import Referral, SessionLocal
from .guardrails import DocumentRejected, validate_document
from .notifications import notify
from .processing import process_referral
from .storage import (
    blob_metadata,
    load_document,
    move_document,
    split_blob_uri,
)

logger = logging.getLogger(__name__)

BLOB_CREATED = "Microsoft.Storage.BlobCreated"


def _decode(raw: str | bytes) -> object | None:
    """Turns a queue message into an event payload.

    Event Grid base64-encodes the event when it writes to a storage queue, but a
    message written by hand or by the local development path is plain JSON. We
    accept both rather than pinning ``messageEncoding`` in host.json, so the same
    handler works no matter who produced the message.
    """
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    try:
        decoded = base64.b64decode(raw, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    try:
        return json.loads(decoded)
    except json.JSONDecodeError:
        return None


def handle_event(raw: str | bytes) -> str | None:
    """Handles one Event Grid message. Returns the referral id, or None if skipped."""
    event = _decode(raw)
    if event is None:
        logger.warning("Discarding a queue message that is not a JSON event.")
        return None

    if isinstance(event, list):
        # Event Grid batches when it is busy; the queue handler sees one at a time.
        results = [handle_event(json.dumps(item)) for item in event]
        return next((result for result in results if result), None)

    if not isinstance(event, dict):
        logger.warning("Discarding a queue message that is not an event object.")
        return None

    if event.get("eventType") != BLOB_CREATED:
        logger.info("Ignoring event type %s.", event.get("eventType"))
        return None

    url = (event.get("data") or {}).get("url")
    if not url:
        logger.warning("Blob created event carried no url.")
        return None

    container, blob_name = split_blob_uri(url)
    if container != settings.incoming_container:
        logger.info("Ignoring a blob created outside the landing zone (%s).", container)
        return None
    return ingest(url, blob_name)


def ingest(storage_uri: str, blob_name: str) -> str | None:
    """Takes a document from the landing zone through to the review queue."""
    try:
        content = load_document(storage_uri)
    except ResourceNotFoundError:
        # A redelivered event for a blob that has already moved on. Nothing to do.
        logger.info("Blob %s is no longer in the landing zone; skipping.", blob_name)
        return None

    metadata = _blob_metadata(storage_uri)

    try:
        filename, content, digest = validate_document(
            blob_name, content, settings.upload_max_bytes
        )
    except DocumentRejected as rejected:
        _quarantine(storage_uri, blob_name, rejected.reason)
        return None

    existing = _existing_referral(digest)
    if existing:
        _quarantine(
            storage_uri,
            filename,
            f"Duplicate of referral {existing} already in the pipeline.",
        )
        return None

    referral_id = str(uuid.uuid4())
    destination = f"{referral_id}/{filename}"

    # Claim the document by moving it out of the landing zone before any other
    # work. The move is what stops a redelivered event from processing the same
    # document twice, so everything after this point is ours to finish or fail.
    processing_uri = move_document(storage_uri, settings.processing_container, destination)

    try:
        with SessionLocal() as session:
            session.add(
                Referral(
                    id=referral_id,
                    filename=filename,
                    sha256=digest,
                    status="processing",
                    progress=10,
                    submitted_by=metadata.get("submittedby", "Upstream system"),
                    source=metadata.get("source", "upstream"),
                    storage_uri=processing_uri,
                )
            )
            session.commit()
        process_referral(referral_id)
    except Exception as error:  # noqa: BLE001 - anything unhandled routes to failed/
        # The document is already claimed, so no retry can reach it again. Record
        # the failure where a reviewer can see it rather than losing it.
        logger.exception("Referral %s failed during processing.", referral_id)
        _fail(referral_id, filename, processing_uri, str(error))
        return None

    logger.info("Referral %s is ready for review.", referral_id)
    return referral_id


def _existing_referral(digest: str) -> str | None:
    with SessionLocal() as session:
        return session.scalar(select(Referral.id).where(Referral.sha256 == digest))


def _blob_metadata(storage_uri: str) -> dict[str, str]:
    try:
        return blob_metadata(storage_uri)
    except Exception:  # noqa: BLE001 - metadata is a nicety, never a blocker
        logger.debug("No metadata available for %s.", storage_uri, exc_info=True)
        return {}


def _quarantine(storage_uri: str, blob_name: str, reason: str) -> None:
    """Routes a document that never became a referral, and says why."""
    logger.warning("Rejecting %s: %s", blob_name, reason)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        move_document(storage_uri, settings.failed_container, f"{stamp}/{blob_name}")
    except Exception:  # noqa: BLE001
        logger.exception("Could not move %s to the failed container.", blob_name)
    notify("referral.rejected", {"filename": blob_name, "reason": reason})


def _fail(referral_id: str, filename: str, storage_uri: str, reason: str) -> None:
    destination = f"{referral_id}/{filename}"
    failed_uri = storage_uri
    try:
        failed_uri = move_document(storage_uri, settings.failed_container, destination)
    except Exception:  # noqa: BLE001
        logger.exception("Could not move referral %s to the failed container.", referral_id)
    with SessionLocal() as session:
        referral = session.get(Referral, referral_id)
        if referral:
            referral.status = "failed"
            referral.progress = 100
            referral.failure_reason = reason[:500]
            referral.storage_uri = failed_uri
            session.commit()
    notify(
        "referral.failed",
        {"referralId": referral_id, "filename": filename, "reason": reason},
    )
