import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from .config import settings
from .database import Referral, SessionLocal, initialize_database
from .guardrails import validate_synthetic_upload
from .identity import current_user
from .processing import process_referral, remember_local_payload
from .storage import enqueue, store_document


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="Referral Intake Reference API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Data-Classification"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


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
    x_data_classification: str | None = Header(default=None),
) -> dict:
    filename, content, digest = await validate_synthetic_upload(
        document, x_data_classification, settings.upload_max_bytes
    )
    with SessionLocal() as session:
        if session.scalar(select(Referral).where(Referral.sha256 == digest)):
            raise HTTPException(409, "This synthetic document has already been submitted.")
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
        asyncio.create_task(asyncio.to_thread(process_referral, referral_id))
    return referral.response()


@app.get("/api/referrals/{referral_id}")
def get_referral(referral_id: str, user: str = Depends(current_user)) -> dict:
    del user
    with SessionLocal() as session:
        referral = session.get(Referral, referral_id)
        if not referral:
            raise HTTPException(404, "Referral not found.")
        return referral.response()


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
