"""Box 6 to Box 7: what a reviewer's decision actually does."""

from pathlib import Path

import pytest

from referral import intake, review
from referral.config import settings
from referral.database import Referral, SessionLocal
from referral.storage import store_incoming
from tests.test_intake import _blob_created_event


def _needs_review(filename: str) -> str:
    uri = store_incoming(filename, f"%PDF {filename}".encode("utf-8"))
    referral_id = intake.handle_event(_blob_created_event(uri, filename))
    assert referral_id
    return referral_id


def _landing_zone(container: str) -> Path:
    return Path(settings.local_landing_zone_root).resolve() / container


def test_an_approved_referral_lands_in_the_archive():
    referral_id = _needs_review("approve-me.pdf")

    decided = review.decide(referral_id, True, "Looks right.", "reviewer@example.com")

    assert decided["status"] == "approved"
    assert (_landing_zone(settings.archive_container) / referral_id / "approve-me.pdf").exists()


def test_a_returned_referral_lands_in_failed():
    referral_id = _needs_review("return-me.pdf")

    decided = review.decide(referral_id, False, "Missing the authorization.", "reviewer@example.com")

    assert decided["status"] == "rejected"
    assert (_landing_zone(settings.failed_container) / referral_id / "return-me.pdf").exists()


def test_the_same_referral_cannot_be_decided_twice():
    referral_id = _needs_review("decide-once.pdf")
    review.decide(referral_id, True, "", "reviewer@example.com")

    with pytest.raises(review.ReviewRejected) as rejected:
        review.decide(referral_id, True, "", "reviewer@example.com")

    assert rejected.value.status == 409


def test_an_unknown_referral_is_a_404():
    with pytest.raises(review.ReviewRejected) as rejected:
        review.decide("not-a-referral", True, "", "reviewer@example.com")

    assert rejected.value.status == 404


def test_an_oversized_note_is_refused_before_anything_moves():
    referral_id = _needs_review("long-note.pdf")

    with pytest.raises(review.ReviewRejected) as rejected:
        review.decide(referral_id, True, "x" * (review.NOTE_MAX_CHARS + 1), "reviewer@example.com")

    assert rejected.value.status == 400
    with SessionLocal() as session:
        assert session.get(Referral, referral_id).status == "needs_review"
