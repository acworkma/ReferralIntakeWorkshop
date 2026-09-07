"""Box 4: turn a claimed document into structured, reviewable evidence.

Called by the orchestration function once a document has been moved into the
``processing`` container. Kept separate from :mod:`referral.intake` so the
extraction step can be driven on its own from the diagnostics CLI.
"""

import json

from sqlalchemy import select

from .database import Referral, SessionLocal
from .extractors import compare
from .storage import load_document


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
        if not referral.storage_uri:
            raise RuntimeError("The referral document is no longer in the landing zone.")
        content = load_document(referral.storage_uri)
        referral.progress = 60
        session.commit()
        referral.comparison_json = json.dumps(compare(content, referral.sha256))
        referral.status = "needs_review"
        referral.progress = 100
        session.commit()
