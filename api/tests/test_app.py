import time

from fastapi.testclient import TestClient

from referral.app import app


def test_referral_reaches_human_review():
    with TestClient(app) as client:
        created = client.post(
            "/api/referrals",
            files={"document": ("demo.pdf", b"%PDF demo document", "application/pdf")},
        )
        assert created.status_code == 202
        referral_id = created.json()["id"]

        referral = created.json()
        for _ in range(40):
            referral = client.get(f"/api/referrals/{referral_id}").json()
            if referral["status"] == "needs_review":
                break
            time.sleep(0.05)

        assert referral["status"] == "needs_review"
        assert referral["comparison"]["rows"]

        reviewed = client.post(
            f"/api/referrals/{referral_id}/review",
            params={"approved": "true", "note": "Verified demonstration."},
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["status"] == "approved"


def test_deleting_a_referral_allows_resubmitting_the_same_document():
    payload = ("resubmit.pdf", b"%PDF resubmission document", "application/pdf")
    with TestClient(app) as client:
        first = client.post("/api/referrals", files={"document": payload})
        assert first.status_code == 202
        referral_id = first.json()["id"]

        duplicate = client.post("/api/referrals", files={"document": payload})
        assert duplicate.status_code == 409

        assert client.delete(f"/api/referrals/{referral_id}").status_code == 204
        assert client.get(f"/api/referrals/{referral_id}").status_code == 404
        assert client.delete(f"/api/referrals/{referral_id}").status_code == 404

        again = client.post("/api/referrals", files={"document": payload})
        assert again.status_code == 202
