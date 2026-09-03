import json

from sqlalchemy import select

from .database import Referral, SessionLocal
from .extractors import compare
from .storage import load_document

_local_payloads: dict[str, bytes] = {}


def remember_local_payload(referral_id: str, content: bytes) -> None:
    _local_payloads[referral_id] = content


def process_referral(referral_id: str) -> None:
    with SessionLocal() as session:
        referral = session.scalar(select(Referral).where(Referral.id == referral_id))
        if not referral:
            return
        if referral.status == "failed":
            raise RuntimeError("Previous processing failed; moving message toward poison queue.")
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
        except (KeyError, OSError, RuntimeError, TypeError, ValueError):
            referral.status = "failed"
            referral.progress = 100
            raise
        finally:
            session.commit()
            _local_payloads.pop(referral_id, None)
