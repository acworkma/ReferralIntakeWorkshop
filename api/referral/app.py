"""Boxes 1 and 6: the two ends of the pipeline the workshop has to stand in for.

This service deliberately does not run the workflow. It drops a document into
the landing zone the way an upstream system would, and it shows a reviewer what
the workflow produced. Everything in between belongs to Event Grid and the
orchestration function, so that the pipeline behaves identically whether a
document arrives from this app, from azcopy, or from a real referral source.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import threading
import uuid

from azure.core.exceptions import AzureError
from fastapi import Depends, FastAPI, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from .analyzer import ensure_analyzer
from .config import settings
from .database import Referral, SessionLocal, initialize_database
from .extractors import _token as _extraction_token
from .identity import current_user
from .intake import handle_event
from .review import ReviewRejected, decide
from .storage import (
    delete_document,
    store_incoming,
    using_azure_storage,
)
from .uploads import validate_upload

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
    # The Azure SDKs log every HTTP request at INFO, which drowns out app logs.
    for noisy in ("azure.core.pipeline.policies.http_logging_policy", "azure.identity"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


_configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    # Analyzer creation is a slow, network-bound call against a private
    # endpoint. Run it off the startup path so a slow or unreachable AI
    # account cannot stall the container's readiness probe.
    threading.Thread(
        target=ensure_analyzer,
        args=(_extraction_token,),
        name="analyzer-provisioner",
        daemon=True,
    ).start()
    yield


app = FastAPI(title="Referral Intake Reference API", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


def _raise_local_event(storage_uri: str, filename: str) -> None:
    """Stands in for Event Grid when there is no storage account.

    In Azure the storage account raises this event itself and Event Grid puts it
    on the queue. On a laptop nothing does, so the same event is synthesised and
    handed to the same handler rather than calling the pipeline a second way.
    """
    event = json.dumps(
        {
            "id": str(uuid.uuid4()),
            "eventType": "Microsoft.Storage.BlobCreated",
            "subject": f"/blobServices/default/containers/{settings.incoming_container}"
            f"/blobs/{filename}",
            "eventTime": datetime.now(timezone.utc).isoformat(),
            "data": {"api": "PutBlob", "url": storage_uri},
        }
    )
    try:
        handle_event(event)
    except Exception:  # noqa: BLE001 - mirrors the function host swallowing and logging
        logger.exception("Local pipeline run failed for %s.", filename)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
        "landingZone": "azure" if using_azure_storage() else "local",
    }


@app.get("/api/me")
def me(user: str = Depends(current_user)) -> dict:
    return {"displayName": user, "localMock": settings.local_mock_identity}


@app.get("/api/referrals")
def list_referrals(user: str = Depends(current_user)) -> list[dict]:
    del user
    with SessionLocal() as session:
        rows = session.scalars(select(Referral).order_by(Referral.created_at.desc())).all()
        return [row.response() for row in rows]


@app.post("/api/referrals", status_code=202)
async def deliver_referral(
    document: UploadFile,
    user: str = Depends(current_user),
) -> dict:
    """Delivers a document to the landing zone, standing in for an upstream system.

    The response deliberately describes a delivery, not a referral. No referral
    exists yet: the blob write raises an event, and the orchestration function
    is what creates the record. Watch the queue for it to appear.
    """
    filename, content, digest = await validate_upload(document, settings.upload_max_bytes)
    with SessionLocal() as session:
        if session.scalar(select(Referral).where(Referral.sha256 == digest)):
            raise HTTPException(409, "This document has already been submitted.")

    storage_uri = store_incoming(
        filename,
        content,
        metadata={"submittedby": user, "source": "web-simulator"},
    )
    if not using_azure_storage():
        threading.Thread(
            target=_raise_local_event,
            args=(storage_uri, filename),
            name=f"local-event-{filename}",
            daemon=True,
        ).start()

    logger.info("Delivered %s to the %s container.", filename, settings.incoming_container)
    return {
        "filename": filename,
        "container": settings.incoming_container,
        "deliveredAt": datetime.now(timezone.utc).isoformat(),
        "message": "Delivered to the landing zone. The workflow picks it up from here.",
    }


@app.get("/api/referrals/{referral_id}")
def get_referral(referral_id: str, user: str = Depends(current_user)) -> dict:
    del user
    with SessionLocal() as session:
        referral = session.get(Referral, referral_id)
        if not referral:
            raise HTTPException(404, "Referral not found.")
        return referral.response()


@app.delete("/api/referrals/{referral_id}", status_code=204)
def delete_referral(referral_id: str, user: str = Depends(current_user)) -> Response:
    del user
    with SessionLocal() as session:
        referral = session.get(Referral, referral_id)
        if not referral:
            raise HTTPException(404, "Referral not found.")
        storage_uri = referral.storage_uri
        session.delete(referral)
        session.commit()
    if storage_uri:
        try:
            delete_document(storage_uri)
        except (AzureError, OSError, ValueError):
            logger.warning("Referral %s row deleted but its document remains.", referral_id)
    return Response(status_code=204)


@app.post("/api/referrals/{referral_id}/review")
def review_referral(
    referral_id: str,
    approved: bool,
    note: str = "",
    user: str = Depends(current_user),
) -> dict:
    """Box 6 to Box 7: records the human decision and hands off to the workflow."""
    try:
        return decide(referral_id, approved, note, user)
    except ReviewRejected as rejected:
        raise HTTPException(rejected.status, rejected.message) from rejected
