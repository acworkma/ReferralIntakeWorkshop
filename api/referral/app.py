import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
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
from .guardrails import validate_upload
from .identity import current_user
from .processing import (
    forget_local_payload,
    mark_failed,
    process_referral,
    remember_local_payload,
)
from .storage import delete_document, enqueue, store_document
from .worker import QueueWorker

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

queue_worker = QueueWorker()


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
    queue_worker.start()
    try:
        yield
    finally:
        queue_worker.stop()


app = FastAPI(title="Referral Intake Reference API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def _process_inline(referral_id: str) -> None:
    """Fallback used only when no queue is configured; the queue worker handles the rest."""
    try:
        process_referral(referral_id)
    except Exception:
        logger.exception("Inline processing failed for referral %s.", referral_id)
        mark_failed(referral_id)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
        "queueWorker": "running" if queue_worker.alive else "stopped",
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
async def create_referral(
    document: UploadFile,
    user: str = Depends(current_user),
) -> dict:
    filename, content, digest = await validate_upload(document, settings.upload_max_bytes)
    with SessionLocal() as session:
        if session.scalar(select(Referral).where(Referral.sha256 == digest)):
            raise HTTPException(409, "This document has already been submitted.")
    referral_id = str(uuid.uuid4())
    storage_uri = store_document(referral_id, filename, content)
    referral = Referral(
        id=referral_id,
        filename=filename,
        sha256=digest,
        status="queued",
        progress=5,
        submitted_by=user,
        storage_uri=storage_uri,
    )
    with SessionLocal() as session:
        session.add(referral)
        session.commit()
    remember_local_payload(referral_id, content)
    if not enqueue(referral_id):
        asyncio.create_task(asyncio.to_thread(_process_inline, referral_id))
    return referral.response()


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
    forget_local_payload(referral_id)
    if storage_uri:
        try:
            delete_document(storage_uri)
        except (AzureError, OSError, ValueError):
            logger.warning("Referral %s row deleted but its blob remains.", referral_id)
    return Response(status_code=204)


@app.post("/api/referrals/{referral_id}/review")
def review_referral(
    referral_id: str,
    approved: bool,
    note: str = "",
    user: str = Depends(current_user),
) -> dict:
    if len(note) > 2000:
        raise HTTPException(400, "Review note cannot exceed 2,000 characters.")
    with SessionLocal() as session:
        referral = session.get(Referral, referral_id)
        if not referral:
            raise HTTPException(404, "Referral not found.")
        if referral.status != "needs_review":
            raise HTTPException(409, "Only referrals awaiting review can be decided.")
        referral.approved = approved
        referral.review_note = note.strip()
        referral.reviewed_by = user
        referral.status = "approved" if approved else "rejected"
        referral.updated_at = datetime.now(timezone.utc)
        session.commit()
        return referral.response()
