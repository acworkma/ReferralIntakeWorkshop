import json

from sqlalchemy import select

from .database import Referral, SessionLocal
from .extractors import compare
from .storage import load_document

_local_payloads: dict[str, bytes] = {}


def remember_local_payload(referral_id: str, content: bytes) -> None:
    _local_payloads[referral_id] = content


def forget_local_payload(referral_id: str) -> None:
    _local_payloads.pop(referral_id, None)


def process_referral(referral_id: str) -> None:
    with SessionLocal() as session:
        referral = session.scalar(select(Referral).where(Referral.id == referral_id))
        if not referral:
            return
        if referral.status not in {"queued", "processing"}:
            return
        referral.status = "processing"
        referral.progress = 25
        session.commit()
        try:
            content = _local_payloads.get(referral_id)
            if content is None and referral.storage_uri:
                content = load_document(referral.storage_uri)
            if content is None:
                raise RuntimeError("Referral document payload is unavailable.")
            referral.progress = 60
            session.commit()
            referral.comparison_json = json.dumps(compare(content, referral.sha256))
            referral.status = "needs_review"
            referral.progress = 100
            session.commit()
        except Exception:
            # Leave the referral in "processing" so the queue retry can try again.
            # mark_failed records the terminal state once retries are exhausted.
            session.rollback()
            raise
        _local_payloads.pop(referral_id, None)


def mark_failed(referral_id: str) -> None:
    """Records the terminal failure once the queue has exhausted its retries."""
    with SessionLocal() as session:
        referral = session.get(Referral, referral_id)
        if not referral or referral.status not in {"queued", "processing"}:
            return
        referral.status = "failed"
        referral.progress = 100
        session.commit()
    _local_payloads.pop(referral_id, None)
