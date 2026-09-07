"""Box 6 to Box 7: the reviewer's decision and the handoff that follows it.

This lives apart from the HTTP layer for the same reason :mod:`referral.intake`
does. A decision is a business event, not a web request: it moves the document
to its final container and tells the Logic App what happened. Keeping it here
means the diagnostics CLI can exercise the real path rather than a copy of it.
"""

from datetime import datetime, timezone
import logging

from azure.core.exceptions import AzureError

from .config import settings
from .database import Referral, SessionLocal
from .notifications import notify
from .storage import move_document

logger = logging.getLogger(__name__)

NOTE_MAX_CHARS = 2000


class ReviewRejected(Exception):
    """Raised when a decision cannot be recorded. Carries an HTTP-ish status."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def decide(referral_id: str, approved: bool, note: str, reviewed_by: str) -> dict:
    """Records a human decision and hands the referral off to the workflow."""
    if len(note) > NOTE_MAX_CHARS:
        raise ReviewRejected(400, f"Review note cannot exceed {NOTE_MAX_CHARS:,} characters.")

    with SessionLocal() as session:
        referral = session.get(Referral, referral_id)
        if not referral:
            raise ReviewRejected(404, "Referral not found.")
        if referral.status != "needs_review":
            raise ReviewRejected(409, "Only referrals awaiting review can be decided.")
        referral.approved = approved
        referral.review_note = note.strip()
        referral.reviewed_by = reviewed_by
        referral.status = "approved" if approved else "rejected"
        referral.updated_at = datetime.now(timezone.utc)
        if referral.storage_uri:
            destination = (
                settings.archive_container if approved else settings.failed_container
            )
            try:
                referral.storage_uri = move_document(
                    referral.storage_uri,
                    destination,
                    f"{referral_id}/{referral.filename}",
                )
            except (AzureError, OSError, ValueError):
                logger.warning(
                    "Referral %s decided but its document stayed in place.", referral_id
                )
        session.commit()
        decided = referral.response()

    # Routing to a system of record and notifying the requester are business
    # decisions, so they belong in the Logic App rather than in this module.
    notify(
        "referral.approved" if approved else "referral.returned",
        {
            "referralId": referral_id,
            "filename": decided["filename"],
            "reviewedBy": reviewed_by,
            "reviewNote": decided["reviewNote"],
            "extraction": decided["comparison"],
        },
    )
    return decided
